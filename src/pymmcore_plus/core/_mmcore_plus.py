from __future__ import annotations

import atexit
import os
import re
import warnings
import weakref
from collections import defaultdict
from contextlib import contextmanager, suppress
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from threading import RLock, Thread
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterable,
    Iterator,
    Pattern,
    Sequence,
    TypeVar,
    cast,
    overload,
)

import pymmcore
from psygnal import SignalInstance

from .._logger import current_logfile, logger
from .._util import find_micromanager, print_tabular_data
from ..mda import MDAEngine, MDARunner, PMDAEngine
from ._adapter import DeviceAdapter
from ._config import Configuration
from ._config_group import ConfigGroup
from ._constants import DeviceDetectionStatus, DeviceType, PropertyType
from ._device import Device
from ._metadata import Metadata
from ._property import DeviceProperty
from ._sequencing import can_sequence_events
from .events import CMMCoreSignaler, PCoreSignaler, _get_auto_core_callback_class

if TYPE_CHECKING:
    import numpy as np
    from typing_extensions import Literal, TypedDict
    from useq import MDAEvent

    _T = TypeVar("_T")
    _F = TypeVar("_F", bound=Callable[..., Any])
    ListOrTuple = list[_T] | tuple[_T, ...]

    class StateDict(TypedDict, total=False):
        """Dictionary of state values for a device.

        This object should only be imported inside a `TYPE_CHECKING` block.
        """

        AutoFocusDevice: str
        BytesPerPixel: int
        CameraChannelNames: tuple[str, ...]
        CameraDevice: str
        Datetime: str
        Exposure: float
        FocusDevice: str
        GalvoDevice: str
        ImageBitDepth: int
        ImageHeight: int
        ImageProcessorDevice: str
        ImageWidth: int
        PixelSizeUm: float
        ShutterDevice: str
        SLMDevice: str
        XYPosition: tuple[float, float]
        XYStageDevice: str
        ZPosition: float

    class PropertySchema(TypedDict, total=False):
        """JSON schema `dict` describing a device property."""

        type: str
        maximum: float
        minimum: float
        enum: list
        readOnly: bool
        default: Any
        sequenceable: bool
        sequenceMaxLength: int
        preInit: bool

    class DeviceSchema(TypedDict):
        """JSON schema `dict` describing a device."""

        title: str
        description: str
        type: str
        properties: dict[str, PropertySchema]

    def synchronized(lock: RLock) -> Callable[[_F], _F]:
        ...

else:
    from wrapt import synchronized

_OBJDEV_REGEX = re.compile("(.+)?(nosepiece|obj(ective)?)(turret)?s?", re.IGNORECASE)
_CHANNEL_REGEX = re.compile("(chan{1,2}(el)?|filt(er)?)s?", re.IGNORECASE)

STATE = pymmcore.g_Keyword_State
LABEL = pymmcore.g_Keyword_Label
STATE_PROPS = (STATE, LABEL)
UNNAMED_PRESET = "NewPreset"


@contextmanager
def _blockSignal(obj: Any, signal: Any) -> Iterator[None]:
    if isinstance(signal, SignalInstance):
        signal.block()
        yield
        signal.unblock()
    else:
        obj.blockSignals(True)
        yield
        obj.blockSignals(False)


_instance = None


class CMMCorePlus(pymmcore.CMMCore):
    """Wrapper for CMMCore with extended functionality.

    Parameters
    ----------
    mm_path : str | None, optional
        Path to the Micro-Manager installation. If `None` (default), will use the
        return value of [`pymmcore_plus.find_micromanager`][].
    adapter_paths : Sequence[str], optional
        Paths to search for device adapters, by default ()
    """

    _lock = RLock()

    @classmethod
    def instance(cls) -> CMMCorePlus:
        """Return the global singleton instance of `CMMCorePlus`.

        :sparkles: *This method is new in `CMMCorePlus`.*

        In many cases, a single instance of `CMMCorePlus` is all that will be created
        in a given session.  This class method provides a convenient way to access
        that instance.

        !!! tip

            Creating/accessing a `CMMCorePlus` object using `CMMCorePlus.instance()` is
            a convenient way to access the same core instance from multiple places in
            your code. All widgets in
            [`pymmcore-widgets`](https://github.com/pymmcore-plus/pymmcore-widgets) also
            use `CMMCorePlus.instance()` by default, so any widgets you use will
            automatically connect to the same core instance without any additional
            configuration.

            Attempts *are* made to make it thread-safe.  But please open an issue
            if you find any problems.


        """
        global _instance
        if _instance is None:
            _instance = cls()
        return _instance

    def __init__(self, mm_path: str | None = None, adapter_paths: Sequence[str] = ()):
        super().__init__()

        if logfile := current_logfile(logger):
            self.setPrimaryLogFile(str(logfile))
            logger.debug("Initialized core {}", self)

        self._mm_path = mm_path or find_micromanager()
        if not adapter_paths and self._mm_path:
            adapter_paths = [self._mm_path]
        if adapter_paths:
            self.setDeviceAdapterSearchPaths(adapter_paths)

        self._events = _get_auto_core_callback_class()()
        self._callback_relay = MMCallbackRelay(self.events)
        self.registerCallback(self._callback_relay)

        self._mda_runner = MDARunner()
        self._mda_runner.set_engine(MDAEngine(self))

        self._objective_regex: Pattern = _OBJDEV_REGEX
        self._channel_group_regex: Pattern = _CHANNEL_REGEX

        # use weakref to avoid atexit keeping us from being
        # garbage collected
        self._weak_clean = weakref.WeakMethod(self.unloadAllDevices)
        atexit.register(self._weak_clean)

    @property
    def events(self) -> PCoreSignaler:
        """Signaler for core events.

        :sparkles: *This method is new in `CMMCorePlus`.*

        This attribute allows connecting callbacks to various events that occur within
        the core. See [`pymmcore_plus.core.events.PCoreSignaler`][] documentation for
        details of the available signals, and how to connect to them.
        """
        return self._events

    def __repr__(self) -> str:
        return f"<{type(self).__name__} at {hex(id(self))}>"

    def __del__(self) -> None:
        atexit.unregister(self._weak_clean)
        self.unloadAllDevices()

    # Re-implemented methods from the CMMCore API

    @synchronized(_lock)
    def setProperty(
        self, label: str, propName: str, propValue: bool | float | int | str
    ) -> None:
        """Set property named `propName` on device `label` to `propValue`.

        **Why Override?**  In `MMCore`, the calling of the `onPropertyChanged`
        callback is left to the underlying device adapter, which means it is not always
        called.  This method overrides the default implementation to ensure that
        `events.propertyChanged` is *always* emitted when `setProperty` has been called
        and the property Value has actually changed.
        """
        with self._property_change_emission_ensured(label, (propName,)):
            super().setProperty(label, propName, propValue)

    @synchronized(_lock)
    def setState(self, stateDeviceLabel: str, state: int) -> None:
        """Set state (by position) on `stateDeviceLabel`, with reliable event emission.

        **Why Override?**  In `MMCore`, the calling of the `onPropertyChanged`
        callback is left to the underlying device adapter, which means it is not always
        called.  This method overrides the default implementation to ensure that
        `events.propertyChanged` is *always* emitted when `setProperty` has been called
        and the property Value has actually changed.
        """
        with self._property_change_emission_ensured(stateDeviceLabel, STATE_PROPS):
            super().setState(stateDeviceLabel, state)

    @synchronized(_lock)
    def setStateLabel(self, stateDeviceLabel: str, stateLabel: str) -> None:
        """Set state (by label) on `stateDeviceLabel`, with reliable event emission.

        **Why Override?**  In `MMCore`, the calling of the `onPropertyChanged`
        callback is left to the underlying device adapter, which means it is not always
        called.  This method overrides the default implementation to ensure that
        `events.propertyChanged` is *always* emitted when `setProperty` has been called
        and the property Value has actually changed.
        """
        with self._property_change_emission_ensured(stateDeviceLabel, STATE_PROPS):
            super().setStateLabel(stateDeviceLabel, stateLabel)

    def setDeviceAdapterSearchPaths(self, paths: Sequence[str]) -> None:
        """Set the device adapter search paths.

        **Why Override?**  In cases where MM device adapters use dynamically loaded
        libraries, the device adapter search paths must also be added to the `PATH`
        environment variable (e.g.
        <https://github.com/micro-manager/pymmcore/issues/28>). This method overrides
        the default implementation to ensure that the `PATH` environment variable is
        updated when the device adapter search paths are changed.
        """
        # add to PATH as well for dynamic dlls
        if not paths:
            return
        if isinstance(paths, str) or any(not isinstance(p, str) for p in paths):
            raise TypeError("paths must be a sequence of strings")
        env_path = os.environ["PATH"]
        for p in paths:
            if p not in env_path:
                env_path = p + os.pathsep + env_path
        os.environ["PATH"] = env_path
        logger.debug(f"setting adapter search paths: {paths}")
        super().setDeviceAdapterSearchPaths(paths)

    def loadDevice(self, label: str, moduleName: str, deviceName: str) -> None:
        """Load a device from the plugin library.

        **Why Override?** To add much better error messages in the case of failure.

        Parameters
        ----------
        label: str
            Name to be assigned to the device during this core session.
        moduleName: str
            The name of the device adapter module (short name, not full file name).
            See [`pymmcore.CMMCore.getDeviceAdapterNames`][] for a list of valid
            module names.
        deviceName: str
            the name of the device. The name must correspond to one of the names
            recognized by the specific plugin library. See
            [`pymmcore.CMMCore.getAvailableDevices`][] for a list of valid device names.
        """
        try:
            super().loadDevice(label, moduleName, deviceName)
        except RuntimeError as e:
            msg = str(e)
            if label in self.getLoadedDevices():
                lib = super().getDeviceLibrary(label)
                name = super().getDeviceName(label)
                if moduleName == lib and deviceName == name:
                    msg += f". Device {label!r} appears to be loaded already."
                    warnings.warn(msg, stacklevel=2)
                    return

                msg += f". Device {label!r} is already taken by {lib}::{name}"
            else:
                adapters = super().getDeviceAdapterNames()
                if moduleName not in adapters:
                    msg += (
                        f". Adapter name {moduleName!r} not in list of known adapter "
                        f"names: {adapters}."
                    )
                else:
                    devices = super().getAvailableDevices(moduleName)
                    if deviceName not in devices:
                        msg += (
                            f". Device name {deviceName!r} not in devices provided by "
                            f"adapter {moduleName!r}: {devices}"
                        )
            raise RuntimeError(msg) from e

    @synchronized(_lock)
    def loadSystemConfiguration(
        self, fileName: str | Path = "MMConfig_demo.cfg"
    ) -> None:
        """Load a system config file conforming to the MM `.cfg` format.

        https://micro-manager.org/Micro-Manager_Configuration_Guide#configuration-file-syntax

        For relative paths, the current working directory is first checked, then the
        then device adapter path is checked.

        **Why Override?** This method overrides the default implementation to A) allow
        loading the `MMConfig_demo.cfg` file by default, B) to provide more flexible
        path declarations and C) better error messages when the file cannot be found.
        """
        fpath = Path(fileName).expanduser()
        if not fpath.exists() and not fpath.is_absolute() and self._mm_path:
            fpath = Path(self._mm_path) / fileName
        if not fpath.exists():
            raise FileNotFoundError(f"Path does not exist: {fpath}")
        super().loadSystemConfiguration(str(fpath.resolve()))

    def unloadAllDevices(self) -> None:
        """Unload all devices from the core and reset all configuration data.

        **Why Override?** To add logging.
        """
        # this log won't appear when exiting ipython, but the method is still called
        logger.debug("Unloading all devices")
        return super().unloadAllDevices()

    def getDeviceType(self, label: str) -> DeviceType:
        """Return device type for a given device.

        **Why Override?** The returned [`pymmcore_plus.Device`][] enum is more
        interpretable than the raw `int` returned by `pymmcore`
        """
        return DeviceType(super().getDeviceType(label))

    def getPropertyType(self, label: str, propName: str) -> PropertyType:
        """Return the intrinsic property type for a given device and property.

        **Why Override?** The returned [`pymmcore_plus.PropertyType`][] enum is more
        interpretable than the raw `int` returned by `pymmcore`
        """
        return PropertyType(super().getPropertyType(label, propName))

    def detectDevice(self, deviceLabel: str) -> DeviceDetectionStatus:
        """Tries to communicate to a device through a given serial port.

        Used to automate discovery of correct serial port.
        Also configures the serial port correctly.

        **Why Override?** The returned [`pymmcore_plus.DeviceDetectionStatus`][] enum
        is more interpretable than the raw `int` returned by `pymmcore`
        """
        return DeviceDetectionStatus(super().detectDevice(deviceLabel))

    # config overrides

    @overload
    def getConfigData(
        self, configGroup: str, configName: str, *, native: Literal[True]
    ) -> pymmcore.Configuration:
        ...

    @overload
    def getConfigData(
        self, configGroup: str, configName: str, *, native: Literal[False] = False
    ) -> Configuration:
        ...

    def getConfigData(
        self, configGroup: str, configName: str, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        """Return the configuration object for a given `configGroup` and `configName`.

        **Why Override?** The [`pymmcore_plus.Configuration`][] object returned
        when `native=False` (the default) provides a nicer `Mapping` interface. Pass
        `native=True` to get the original `pymmcore.Configuration` object.
        """
        cfg = super().getConfigData(configGroup, configName)
        return cfg if native else Configuration.from_configuration(cfg)

    @overload
    def getPixelSizeConfigData(
        self, configName: str, *, native: Literal[True]
    ) -> pymmcore.Configuration:
        ...

    @overload
    def getPixelSizeConfigData(
        self, configName: str, *, native: Literal[False] = False
    ) -> Configuration:
        ...

    def getPixelSizeConfigData(
        self, configName: str, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        """Return the configuration object for a given pixel size preset `configName`.

        **Why Override?** The [`pymmcore_plus.Configuration`][] object returned
        when `native=False` (the default) provides a nicer `Mapping` interface. Pass
        `native=True` to get the original `pymmcore.Configuration` object.
        """
        cfg = super().getPixelSizeConfigData(configName)
        return cfg if native else Configuration.from_configuration(cfg)

    @overload
    def getConfigGroupState(
        self, group: str, *, native: Literal[True]
    ) -> pymmcore.Configuration:
        ...

    @overload
    def getConfigGroupState(
        self, group: str, *, native: Literal[False] = False
    ) -> Configuration:
        ...

    def getConfigGroupState(
        self, group: str, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        """Return the state of the devices included in the specified `group`.

        **Why Override?** The [`pymmcore_plus.Configuration`][] object returned
        when `native=False` (the default) provides a nicer `Mapping` interface. Pass
        `native=True` to get the original `pymmcore.Configuration` object.
        """
        cfg = super().getConfigGroupState(group)
        return cfg if native else Configuration.from_configuration(cfg)

    def getConfigGroupStateFromCache(
        self, group: str, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        """Return the state of the system cache, for the devices in the specified group.

        **Why Override?** The [`pymmcore_plus.Configuration`][] object returned
        when `native=False` (the default) provides a nicer `Mapping` interface. Pass
        `native=True` to get the original `pymmcore.Configuration` object.
        """
        cfg = super().getConfigGroupStateFromCache(group)
        return cfg if native else Configuration.from_configuration(cfg)

    def getConfigState(
        self, group: str, config: str, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        """Return state of devices included in the specified configuration.

        **Why Override?** The [`pymmcore_plus.Configuration`][] object returned
        when `native=False` (the default) provides a nicer `Mapping` interface. Pass
        `native=True` to get the original `pymmcore.Configuration` object.
        """
        cfg = super().getConfigState(group, config)
        return cfg if native else Configuration.from_configuration(cfg)

    def getSystemState(
        self, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        """Return the entire system state.

        **Why Override?** The [`pymmcore_plus.Configuration`][] object returned
        when `native=False` (the default) provides a nicer `Mapping` interface. Pass
        `native=True` to get the original `pymmcore.Configuration` object.
        """
        cfg = super().getSystemState()
        return cfg if native else Configuration.from_configuration(cfg)

    def getSystemStateCache(
        self, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        """Return the entire system state from cache.

        **Why Override?** The [`pymmcore_plus.Configuration`][] object returned
        when `native=False` (the default) provides a nicer `Mapping` interface. Pass
        `native=True` to get the original `pymmcore.Configuration` object.
        """
        cfg = super().getSystemStateCache()
        return cfg if native else Configuration.from_configuration(cfg)

    # metadata methods that don't require instantiating metadata first

    @overload
    def getLastImageAndMD(
        self, channel: int, slice: int, *, fix: bool = True
    ) -> tuple[np.ndarray, Metadata]:
        ...

    @overload
    def getLastImageAndMD(self, *, fix: bool = True) -> tuple[np.ndarray, Metadata]:
        ...

    @synchronized(_lock)
    def getLastImageAndMD(
        self, channel: int | None = None, slice: int | None = None, *, fix: bool = True
    ) -> tuple[np.ndarray, Metadata]:
        """Return last image from the circular buffer along with metadata.

        :sparkles: *This method is new in `CMMCorePlus`.*

        This is a convenience method that is very similar to `getLastImageMD`, except
        that it doesn't require instantiating a `MetaData` object first. It returns a
        tuple containing the image and a [`pymmcore_plus.Metadata`][] object.

        It also adds a `fix` parameter, which reshapes multi-component
        images (like RGB images) to (w, h, n_components) using
        [`fixImage`][pymmcore_plus.CMMCorePlus.fixImage] by default.

        Parameters
        ----------
        channel : int, optional
            Channel index, by default None
        slice : int, optional
            Slice index, by default None
        fix : bool, default: True
            If `True` (the default), then images with n_components > 1 (like RGB images)
            will be reshaped to (w, h, n_components) using `fixImage`.

        Returns
        -------
        tuple[np.ndarray, Metadata]
            Image and metadata
        """
        md = Metadata()
        if channel is not None and slice is not None:
            img = super().getLastImageMD(channel, slice, md)
        else:
            img = super().getLastImageMD(md)
        return (self.fixImage(img) if fix else img, md)

    @overload
    def popNextImageAndMD(self, channel: int, slice: int, *, fix: bool = True) -> Any:
        ...

    @overload
    def popNextImageAndMD(self, *, fix: bool = True) -> Any:
        ...

    @synchronized(_lock)
    def popNextImageAndMD(
        self, channel: int | None = None, slice: int | None = None, *, fix: bool = True
    ) -> tuple[np.ndarray, Metadata]:
        """Gets and removes the next image (and metadata) from the circular buffer.

        :sparkles: *This method is new in `CMMCorePlus`.*

        This is a convenience method that is very similar to `popNextImageMD`, except
        that it doesn't require instantiating a `MetaData` object first. It returns a
        tuple containing the image and a [`pymmcore_plus.Metadata`][] object.

        It also adds a `fix` parameter, which reshapes multi-component
        images (like RGB images) to (w, h, n_components) using
        [`fixImage`][pymmcore_plus.CMMCorePlus.fixImage] by default.

        Parameters
        ----------
        channel : int, optional
            Channel index, by default None
        slice : int, optional
            Slice index, by default None
        fix : bool, default: True
            If `True` (the default), then images with n_components > 1 (like RGB images)
            will be reshaped to (w, h, n_components) using `fixImage`.

        Returns
        -------
        tuple[np.ndarray, Metadata]
            Image and metadata
        """
        md = Metadata()
        if channel is not None and slice is not None:
            img = super().popNextImageMD(channel, slice, md)
        else:
            img = super().popNextImageMD(md)
        return (self.fixImage(img) if fix else img, md)

    @synchronized(_lock)
    def popNextImage(self, *, fix: bool = True) -> np.ndarray:
        """Gets and removes the next image from the circular buffer.

        **Why Override?** to add the `fix` parameter, which reshapes multi-component
        images (like RGB images) to (w, h, n_components) using
        [`fixImage`][pymmcore_plus.CMMCorePlus.fixImage] by default.

        Parameters
        ----------
        fix : bool, default: True
            If `True` (the default), then images with n_components > 1 (like RGB images)
            will be reshaped to (w, h, n_components) using `fixImage`.
        """
        img: np.ndarray = super().popNextImage()
        return self.fixImage(img) if fix else img

    @synchronized(_lock)
    def getNBeforeLastImageAndMD(
        self, n: int, *, fix: bool = True
    ) -> tuple[np.ndarray, Metadata]:
        """Return image taken `n` images ago along with associated metadata.

        :sparkles: *This method is new in `CMMCorePlus`.*

        This is a convenience method that is very similar to `getNBeforeLastImageMD`,
        except that it doesn't require instantiating a `MetaData` object first. It
        returns a tuple containing the image and a [`pymmcore_plus.Metadata`][] object.

        It also adds a `fix` parameter, which reshapes multi-component
        images (like RGB images) to (w, h, n_components) using
        [`fixImage`][pymmcore_plus.CMMCorePlus.fixImage] by default.

        Parameters
        ----------
        n : int
            The number of images ago to retrieve. 0 is the last image, 1 is the
            image before that, etc.
        fix : bool, default: True
            If `True` (the default), then images with n_components > 1 (like RGB images)
            will be reshaped to (w, h, n_components) using `fixImage`.
        """
        md = Metadata()
        img = super().getNBeforeLastImageMD(n, md)
        return self.fixImage(img) if fix else img, md

    def setConfig(self, groupName: str, configName: str) -> None:
        """Applies a configuration to a group.

        **Why Override?** The native `onConfigGroupChanged` callback is not always
        called whenever `CMMCore.setConfig` has been called. We override here to emit
        a `configSet` event whenever `setConfig` is called.
        See <https://github.com/micro-manager/mmCoreAndDevices/issues/25> for details.
        """
        super().setConfig(groupName, configName)
        self.events.configSet.emit(groupName, configName)

    # NEW methods

    @overload
    def iterDeviceAdapters(
        self,
        adapter_pattern: str | re.Pattern | None = ...,
        *,
        as_object: Literal[True] = ...,
    ) -> Iterator[DeviceAdapter]:
        ...

    @overload
    def iterDeviceAdapters(
        self,
        adapter_pattern: str | re.Pattern | None = ...,
        *,
        as_object: Literal[False],
    ) -> Iterator[str]:
        ...

    def iterDeviceAdapters(
        self,
        adapter_pattern: str | re.Pattern | None = None,
        *,
        as_object: bool = True,
    ) -> Iterator[DeviceAdapter] | Iterator[str]:
        """Iterate over all available device adapters.

        :sparkles: *This method is new in `CMMCorePlus`.*

        It offers a convenient way to iterate over availabe device adaptor libraries,
        optionally filtering adapter library name. It can also yield
        [`Adapter`][pymmcore_plus.DeviceAdapter] objects if `as_object` is `True` (the
        default)

        Parameters
        ----------
        adapter_pattern : str | None
            Device adapter name or pattern to filter by, by default all device adapters
            will be yielded.
        as_object : bool, optional
            If `True`, `Adapter` objects will be yielded instead of
            library name strings. By default True

        Yields
        ------
        Device | str
            `Device` objects (if `as_object==True`) or device label strings.
        """
        adapters: Sequence[str] = super().getDeviceAdapterNames()

        if adapter_pattern:
            if isinstance(adapter_pattern, str):
                ptrn = re.compile(adapter_pattern, re.IGNORECASE)
            else:
                ptrn = adapter_pattern
            adapters = [d for d in adapters if ptrn.search(d)]

        for adapter in adapters:
            yield DeviceAdapter(adapter, mmcore=self) if as_object else adapter

    @overload
    def iterDevices(
        self,
        device_type: int | Iterable[int] | None = ...,
        device_label: str | re.Pattern | None = ...,
        device_adapter: str | re.Pattern | None = ...,
        *,
        as_object: Literal[False],
    ) -> Iterator[str]:
        ...

    @overload
    def iterDevices(
        self,
        device_type: int | Iterable[int] | None = ...,
        device_label: str | re.Pattern | None = ...,
        device_adapter: str | re.Pattern | None = ...,
        *,
        as_object: Literal[True] = ...,
    ) -> Iterator[Device]:
        ...

    def iterDevices(
        self,
        device_type: int | Iterable[int] | None = None,
        device_label: str | re.Pattern | None = None,
        device_adapter: str | re.Pattern | None = None,
        *,
        as_object: bool = True,
    ) -> Iterator[Device] | Iterator[str]:
        """Iterate over currently loaded devices.

        :sparkles: *This method is new in `CMMCorePlus`.*

        It offers a convenient way to iterate over loaded devices, optionally filtering
        by [`DeviceType`][pymmcore_plus.DeviceType] and/or device label. It can also
        yield [`Device`][pymmcore_plus.Device] objects if `as_object` is
        `True` (the default).

        Parameters
        ----------
        device_type : DeviceType | None
            DeviceType to filter by, by default all device types will be yielded.
        device_label : str | None
            Device label to filter by, by default all device labels will be yielded.
        device_adapter : str | None
            Device adapter library to filter by, by default devices from all libraries
            will be yielded.
        as_object : bool, optional
            If `True`, `Device` objects will be yielded instead of
            device label strings. By default True

        Yields
        ------
        Device | str
            `Device` objects (if `as_object==True`) or device label strings.
        """
        if device_type is None:
            devices: Sequence[str] = self.getLoadedDevices()
        elif isinstance(device_type, int):
            devices = self.getLoadedDevicesOfType(device_type)
        else:
            _devices: set[str] = set()
            for dtype in device_type:
                _devices.update(self.getLoadedDevicesOfType(dtype))
            devices = list(_devices)

        if device_label:
            if isinstance(device_label, str):
                ptrn = re.compile(device_label, re.IGNORECASE)
            else:
                ptrn = device_label
            devices = [d for d in devices if ptrn.search(d)]

        if device_adapter:
            if isinstance(device_adapter, str):
                ptrn = re.compile(device_adapter, re.IGNORECASE)
            else:
                ptrn = device_adapter
            devices = [d for d in devices if ptrn.search(self.getDeviceLibrary(d))]

        for dev in devices:
            yield Device(dev, mmcore=self) if as_object else dev

    @overload
    def iterProperties(
        self,
        property_type: int | Iterable[int] | None = ...,
        property_name_pattern: str | re.Pattern | None = ...,
        *,
        device_type: int | Iterable[int] | None = ...,
        device_label: str | re.Pattern | None = ...,
        has_limits: bool | None = None,
        is_read_only: bool | None = None,
        is_sequenceable: bool | None = None,
        as_object: Literal[False],
    ) -> Iterator[tuple[str, str]]:
        ...

    @overload
    def iterProperties(
        self,
        property_type: int | Iterable[int] | None = ...,
        property_name_pattern: str | re.Pattern | None = ...,
        *,
        device_type: int | Iterable[int] | None = ...,
        device_label: str | re.Pattern | None = ...,
        has_limits: bool | None = None,
        is_read_only: bool | None = None,
        is_sequenceable: bool | None = None,
        as_object: Literal[True] = ...,
    ) -> Iterator[DeviceProperty]:
        ...

    def iterProperties(
        self,
        property_type: int | Iterable[int] | None = None,
        property_name_pattern: str | re.Pattern | None = None,
        *,
        device_type: int | Iterable[int] | None = None,
        device_label: str | re.Pattern | None = None,
        has_limits: bool | None = None,
        is_read_only: bool | None = None,
        is_sequenceable: bool | None = None,
        as_object: bool = True,
    ) -> Iterator[DeviceProperty] | Iterator[tuple[str, str]]:
        """Iterate over currently loaded (device_label, property_name) pairs.

        :sparkles: *This method is new in `CMMCorePlus`.*

        It offers a convenient way to iterate over loaded devices, optionally filtering
        by [`DeviceType`][pymmcore_plus.DeviceType] and/or device label. It can also
        yields [`DeviceProperty`][pymmcore_plus.DeviceProperty] objects if
        `as_object` is `True` (the default).

        Parameters
        ----------
        property_type : int | Sequence[int] | None
            PropertyType (or types) to filter by, by default all property types will
            be yielded.
        property_name_pattern : str | re.Pattern | None
            Property name to filter by, by default all property names will be yielded.
            May be a compiled regular expression or a string, in which case it will be
            compiled with `re.IGNORECASE`.
        device_type : DeviceType | None
            DeviceType to filter by, by default all device types will be yielded.
        device_label : str | None
            Device label to filter by, by default all device labels will be yielded.
        has_limits : bool | None
            If provided, only properties with `hasPropertyLimits` matching this value
            will be yielded.
        is_read_only : bool | None
            If provided, only properties with `isPropertyReadOnly` matching this value
            will be yielded.
        is_sequenceable : bool | None
            If provided only properties with `isPropertySequenceable` matching this
            value will be yielded.
        as_object : bool, optional
            If `True`, `DeviceProperty` objects will be yielded instead of
            `(device_label, property_name)` tuples. By default True

        Yields
        ------
        DeviceProperty | tuple[str, str]
            `DeviceProperty` objects (if `as_object==True`) or 2-tuples of (device_name,
            property_name)
        """
        if property_name_pattern:
            if isinstance(property_name_pattern, str):
                ptrn = re.compile(property_name_pattern, re.IGNORECASE)
            else:
                ptrn = property_name_pattern
        else:
            ptrn = None

        if property_type is None:
            property_types = set()
        elif isinstance(property_type, int):
            property_types = {property_type}
        else:
            property_types = set(property_type)

        for dev in self.iterDevices(device_type, device_label, as_object=False):
            for prop in self.getDevicePropertyNames(dev):
                if ptrn and not ptrn.search(prop):
                    continue
                if (
                    property_type is not None
                    and super().getPropertyType(dev, prop) not in property_types
                ):
                    continue
                if (
                    has_limits is not None
                    and self.hasPropertyLimits(dev, prop) != has_limits
                ):
                    continue
                if (
                    is_read_only is not None
                    and self.isPropertyReadOnly(dev, prop) != is_read_only
                ):
                    continue
                if (
                    is_sequenceable is not None
                    and self.isPropertySequenceable(dev, prop) != is_sequenceable
                ):
                    continue

                yield DeviceProperty(dev, prop, self) if as_object else (dev, prop)

    def getPropertyObject(
        self, device_label: str, property_name: str
    ) -> DeviceProperty:
        """Return a DeviceProperty object bound to a device/property on this core.

        :sparkles: *This method is new in `CMMCorePlus`.*

        [`DeviceProperty`][pymmcore_plus.DeviceProperty] objects are a convenient object
        oriented way to interact with a specific device properties. They allow you to
        call any method on `CMMCore` that normally requires a `deviceLabel` and
        `propertyName` as the first two arguments as an argument-free method on the
        `DeviceProperty` object.

        Parameters
        ----------
        device_label : str
            Device label to get a property object for.
        property_name : str
            Property name to get a property object for.

        Examples
        --------
        >>> core = CMMCorePlus()
        >>> core.loadDevice("DemoCamera", "DemoCamera", "DCam")
        >>> core.initializeDevice("DemoCamera")
        >>> core.setCameraDevice("DemoCamera")
        >>> exposure = core.getPropertyObject("DemoCamera", "Exposure")
        >>> exposure.type()
        <PropertyType.Float: 2>
        >>> exposure.upperLimit()
        10000.0

        get/set propery values easily:

        >>> exposure.value
        10.0
        >>> exposure.value = 5.0
        >>> exposure.value
        5.0
        >>> core.getExposure()  # changes reflected in core
        5.0
        """
        return DeviceProperty(device_label, property_name, self)

    def getAdapterObject(self, library_name: str) -> DeviceAdapter:
        """Return an `Adapter` object bound to library_name on this core.

        :sparkles: *This method is new in `CMMCorePlus`.*

        [`Adapter`][pymmcore_plus.DeviceAdapter] objects are a convenient object
        oriented way to interact with device adapters. They allow you to call any method
        on `CMMCore` that normally requires a `library_name` as the first argument as an
        argument-free method on the `Adapter` object.
        """
        return DeviceAdapter(library_name, mmcore=self)

    def getDeviceObject(self, device_label: str) -> Device:
        """Return a `Device` object bound to device_label on this core.

        :sparkles: *This method is new in `CMMCorePlus`.*

        [`Device`][pymmcore_plus.Device] objects are a convenient object oriented way to
        interact with devices. They allow you to call any method on `CMMCore` that
        normally requires a `deviceLabel` as the first argument as an argument-free
        method on the `Device` object.

        Parameters
        ----------
        device_label : str
            Device label to get a device object for.

        Examples
        --------
        >>> core = CMMCorePlus()
        >>> cam = core.getDeviceObject("DemoCamera")
        >>> cam.isLoaded()
        False
        >>> cam.load("DemoCamera", "DCam")
        >>> cam.isLoaded()
        True
        >>> cam.initialize()

        get the device schema

        >>> cam.schema()
        {
            'title': 'DCam',
            'description': 'Demo camera',
            'type': 'object',
            'properties': {
                'HubID': {'type': 'string', 'readOnly': True, 'default': ''},
                'MaximumExposureMs': {'type': 'number', 'preInit': True},
                'TransposeCorrection': {'type': 'boolean'},
                'TransposeMirrorX': {'type': 'boolean'},
                'TransposeMirrorY': {'type': 'boolean'},
                'TransposeXY': {'type': 'boolean'}
            }
        }
        """
        return Device(device_label, mmcore=self)

    def getConfigGroupObject(
        self, group_name: str, allow_missing: bool = False
    ) -> ConfigGroup:
        """Return a `ConfigGroup` object bound to group_name on this core.

        :sparkles: *This method is new in `CMMCorePlus`.*

        [`ConfigGroup`][pymmcore_plus.ConfigGroup] objects are a convenient object
        oriented way to interact with configuration groups (i.e. groups of
        [Configuration
        Presets](https://micro-manager.org/Micro-Manager_Configuration_Guide#configuration-presets)
        in Micro-Manager). They allow you to call any method on `CMMCore` that normally
        requires a `groupName` as the first argument as an argument-free method on the
        `ConfigGroup` object.

        Parameters
        ----------
        group_name : str
            Configuration group name to get a config group object for.

        Examples
        --------

        """
        group = ConfigGroup(group_name, mmcore=self)
        if not allow_missing and not group.exists():
            raise KeyError(
                f"Configuration group {group_name!r} does not exist. "
                "Use `allow_missing=True` to create create non-existent config groups."
            )
        return group

    def iterConfigGroups(self) -> Iterator[ConfigGroup]:
        """Iterate `ConfigGroup` objects for all configs.

        :sparkles: *This method is new in `CMMCorePlus`.*

        Yields
        ------
        ConfigGroup
            `ConfigGroup` objects
        """
        for group in self.getAvailableConfigGroups():
            yield ConfigGroup(group, mmcore=self)

    def getDeviceSchema(self, device_label: str) -> DeviceSchema:
        """Return JSON-schema describing device `device_label` and its properties.

        :sparkles: *This method is new in `CMMCorePlus`. It provides a convenient way to
        get all of the information about a device in a single call.*

        Returns
        -------
        DeviceSchema
            JSON-schema describing device `device_label` and its properties.

        Examples
        --------
        >>> core = CMMCorePlus()
        >>> core.loadDevice("DemoCamera", "DemoCamera", "DCam")
        >>> core.getDeviceSchema("DemoCamera")
        {
            'title': 'DCam',
            'description': 'Demo camera',
            'type': 'object',
            'properties': {
                'HubID': {'type': 'string', 'readOnly': True, 'default': ''},
                'MaximumExposureMs': {'type': 'number', 'preInit': True},
                'TransposeCorrection': {'type': 'boolean'},
                'TransposeMirrorX': {'type': 'boolean'},
                'TransposeMirrorY': {'type': 'boolean'},
                'TransposeXY': {'type': 'boolean'}
            }
        }
        """
        d: DeviceSchema = {
            "title": self.getDeviceName(device_label),
            "description": self.getDeviceDescription(device_label),
            "type": "object",
            "properties": {},
        }
        for prop in self.iterProperties(device_label=device_label, as_object=True):
            p: PropertySchema
            d["properties"][prop.name] = p = {}
            if prop.type().to_json() != "null":
                p["type"] = prop.type().to_json()
            if prop.hasLimits():
                p["minimum"] = prop.lowerLimit()
                p["maximum"] = prop.upperLimit()
            if allowed := prop.allowedValues():
                if set(allowed) == {"0", "1"} and prop.type() == PropertyType.Integer:
                    p["type"] = "boolean"
                else:
                    cls = prop.type().to_python()
                    p["enum"] = [cls(i) if cls else i for i in allowed]
            if prop.isReadOnly():
                p["readOnly"] = True
                p["default"] = prop.value
            if prop.isSequenceable():
                p["sequenceable"] = True
                p["sequenceMaxLength"] = prop.sequenceMaxLength()
            if prop.isPreInit():
                p["preInit"] = True
        return d

    @property
    def objective_device_pattern(self) -> Pattern:
        """Pattern used to guess objective device labels.

        :sparkles: *This property is new in `CMMCorePlus`.

        It is the regex used by
        [`guessObjectiveDevices`][pymmcore_plus.CMMCorePlus.guessObjectiveDevices] to
        find any devices that are likely to be objective devices.

        By default:

            re.compile("(.+)?(nosepiece|obj(ective)?)(turret)?s?", re.IGNORECASE)
        """
        return self._objective_regex

    @objective_device_pattern.setter
    def objective_device_pattern(self, value: Pattern | str) -> None:
        if isinstance(value, str):
            value = re.compile(value, re.IGNORECASE)
        elif not isinstance(value, Pattern):
            raise TypeError(
                "Objective Pattern must be a string or compiled regex"
                f" but is type {type(value)}"
            )
        self._objective_regex = value

    @property
    def channelGroup_pattern(self) -> Pattern:
        """The regex pattern used to identify channel groups.

        :sparkles: *This property is new in `CMMCorePlus`.

        It is the regex used by
        [`getOrGuessChannelGroup`][pymmcore_plus.CMMCorePlus.getOrGuessChannelGroup] to
        find a config group likely to be a channel group in `getAvailableConfigGroups`
        if `getChannelGroup` returns `None`.

        By default:

            re.compile("(chan{1,2}(el)?|filt(er)?)s?", re.IGNORECASE)
        """
        return self._channel_group_regex

    @channelGroup_pattern.setter
    def channelGroup_pattern(self, value: Pattern | str) -> None:
        if isinstance(value, str):
            value = re.compile(value, re.IGNORECASE)
        elif not isinstance(value, Pattern):
            raise TypeError(
                "channelGroup Pattern must be a string or compiled regex"
                f"but is type {type(value)}"
            )
        self._channel_group_regex = value

    def guessObjectiveDevices(self) -> list[str]:
        """Find any loaded devices that are likely to be an Objective/Nosepiece.

        :sparkles: *This method is new in `CMMCorePlus`.*

        Likely matches are loaded StateDevices with names that match this object's
        `objective_device_pattern` property. This is a settable property
        with a default value of::

            re.compile("(.+)?(nosepiece|obj(ective)?)(turret)?s?", re.IGNORECASE)
        """
        return [
            device
            for device in self.getLoadedDevicesOfType(DeviceType.StateDevice)
            if self._objective_regex.match(device)
        ]

    def getOrGuessChannelGroup(self) -> list[str]:
        """Get the channelGroup or find a likely set of candidates.

        :sparkles: *This method is new in `CMMCorePlus`.*

        If the group is not defined via `.getChannelGroup` then likely candidates
        will be found by searching for config groups with names that match this
        object's `channelGroup_pattern` property. This is a settable property
        with a default value of:

            reg = re.compile("(chan{1,2}(el)?|filt(er)?)s?", re.IGNORECASE)

        """
        # sourcery skip: use-named-expression
        chan_group = self.getChannelGroup()
        if chan_group:
            return [chan_group]
        # not set in core. Try "Channel" and other variations as fallbacks
        return [
            group
            for group in self.getAvailableConfigGroups()
            if self._channel_group_regex.match(group)
        ]

    def setRelativeXYZPosition(
        self, dx: float = 0, dy: float = 0, dz: float = 0
    ) -> None:
        """Sets the relative XYZ position in microns.

        :sparkles: *This method is new in `CMMCorePlus`.*

        This is a convenience method that calls `setXYPosition` and `setZPosition`
        with the current position as the starting point.

        Parameters
        ----------
        dx : float, optional
            The relative change in X position, by default 0
        dy : float, optional
            The relative change in Y position, by default 0
        dz : float, optional
            The relative change in Z position, by default 0
        """
        if dx or dy:
            x, y = self.getXPosition(), self.getYPosition()
            self.setXYPosition(x + dx, y + dy)
        if dz:
            z = self.getPosition(self.getFocusDevice())
            self.setZPosition(z + dz)
        self.waitForDevice(self.getXYStageDevice())
        self.waitForDevice(self.getFocusDevice())

    def getZPosition(self) -> float:
        """Obtains the current position of the Z axis of the Z stage in microns.

        :sparkles: *This method is new in `CMMCorePlus`:
        added to complement `getXPosition` and `getYPosition`*
        """
        return self.getPosition(self.getFocusDevice())

    def setZPosition(self, val: float) -> None:
        """Set the position of the current focus device in microns.

        :sparkles: *This method is new in `CMMCorePlus`:
        added to complement `setXYPosition`*
        """
        return self.setPosition(self.getFocusDevice(), val)

    @overload
    def setPosition(self, position: float) -> None:
        ...

    @overload
    def setPosition(self, stageLabel: str, position: float) -> None:
        ...

    @synchronized(_lock)
    def setPosition(self, *args: Any, **kwargs: Any) -> None:
        """Set position of the stage in microns.

        **Why Override?** To add a lock to prevent concurrent calls across threads.
        """
        return super().setPosition(*args, **kwargs)

    @overload
    def setXYPosition(self, x: float, y: float) -> None:
        ...

    @overload
    def setXYPosition(self, xyStageLabel: str, x: float, y: float) -> None:
        ...

    @synchronized(_lock)
    def setXYPosition(self, *args: Any, **kwargs: Any) -> None:
        """Sets the position of the XY stage in microns.

        **Why Override?** To add a lock to prevent concurrent calls across threads.
        """
        return super().setXYPosition(*args, **kwargs)

    @synchronized(_lock)
    def getCameraChannelNames(self) -> tuple[str, ...]:
        """Convenience method to call `getCameraChannelName` for all camera channels.

        :sparkles: *This method is new in `CMMCorePlus`.*
        """
        return tuple(
            self.getCameraChannelName(i)
            for i in range(self.getNumberOfCameraChannels())
        )

    @synchronized(_lock)
    def snapImage(self) -> None:
        """Acquires a single image with current settings.

        **Why Override?** To add a lock to prevent concurrent calls across threads.
        """
        autoshutter = self.getAutoShutter()
        if autoshutter:
            self.events.propertyChanged.emit(self.getShutterDevice(), "State", True)
        try:
            super().snapImage()
        finally:
            if autoshutter:
                self.events.propertyChanged.emit(
                    self.getShutterDevice(), "State", False
                )

    @property
    def mda(self) -> MDARunner:
        """Return the `MDARunner` for this `CMMCorePlus` instance.

        :sparkles: *This method is new in `CMMCorePlus`.*
        """
        return self._mda_runner

    def run_mda(self, events: Iterable[MDAEvent], block: bool = False) -> Thread:
        """Run a sequence of [useq.MDAEvent][] on a new thread.

        :sparkles: *This method is new in `CMMCorePlus`.*

        The currently registered MDAEngine (`core.mda.engine`) will be responsible for
        executing the acquisition.

        After starting the sequence you can pause or cancel with the mda with
        the mda object's `toggle_pause` and `cancel` methods.

        Parameters
        ----------
        events : Iterable[useq.MDAEvent]
            An iterable of [useq.MDAEvent][] to execute.  This may be an instance
            of [useq.MDASequence][], or any other iterable of [useq.MDAEvent][].
        block : bool, optional
            If True, block until the sequence is complete, by default False.

        Returns
        -------
        Thread
            The thread the sequence is running on.  Use `thread.join()` to block until
            done, or `thread.is_alive()` to check if the sequence is complete.
        """
        if self.mda.is_running():
            raise ValueError(
                "Cannot start an MDA while the previous MDA is still running."
            )
        th = Thread(target=self.mda.run, args=(events,))
        th.start()
        if block:
            th.join()
        return th

    def register_mda_engine(self, engine: PMDAEngine) -> None:
        """Set the MDA Engine to be used on `run_mda`.

        :sparkles: *This method is new in `CMMCorePlus`.*

        This will unregister the previous engine and emit an `mdaEngineRegistered`
        signal. The current Engine must not be running an MDA in order to register a new
        engine.

        Parameters
        ----------
        engine : PMDAEngine
            Any object conforming to the PMDAEngine protocol.
        """
        old_engine = self.mda.set_engine(engine)
        self.events.mdaEngineRegistered.emit(engine, old_engine)

    def fixImage(self, img: np.ndarray, ncomponents: int | None = None) -> np.ndarray:
        """Fix img shape/dtype based on `self.getNumberOfComponents()`.

        :sparkles: *This method is new in `CMMCorePlus`.*

        convert images with n_components > 1
        to a shape (w, h, num_components) and dtype `img.dtype.itemsize//ncomp`

        Parameters
        ----------
        img : np.ndarray
            input image
        ncomponents : int, optional
            number of components in the image, by default `self.getNumberOfComponents()`

        Returns
        -------
        np.ndarray
            output image (possibly new shape and dtype)
        """
        if ncomponents is None:
            ncomponents = self.getNumberOfComponents()
        if ncomponents == 4:
            new_shape = (*img.shape, 4)
            img = img.view(dtype=f"u{img.dtype.itemsize//4}")
            img = img.reshape(new_shape)[:, :, (2, 1, 0, 3)]  # mmcore gives bgra
        return img

    def snap(self, numChannel: int | None = None, *, fix: bool = True) -> np.ndarray:
        """Snap and return an image.

        :sparkles: *This method is new in `CMMCorePlus`.*

        Convenience for calling `self.snapImage()` followed by returning the value
        of `self.getImage()`.

        Parameters
        ----------
        numChannel : int, optional
            The camera channel to get the image from.  If None, (the default), then
            Multi-Channel cameras will return the content of the first channel.
        fix : bool, default: True
            If `True` (the default), then images with n_components > 1 (like RGB images)
            will be reshaped to (w, h, n_components) using `fixImage`.

        Returns
        -------
        img : np.ndarray
        """
        self.snapImage()
        img = self.getImage(numChannel, fix=fix)  # type: ignore
        self.events.imageSnapped.emit(img)
        return img

    @overload
    def getImage(self, *, fix: bool = True) -> np.ndarray:
        """Return the internal image buffer."""

    @overload
    def getImage(self, numChannel: int, *, fix: bool = True) -> np.ndarray:
        """Return the internal image buffer for a given Camera Channel"""

    def getImage(
        self, numChannel: int | None = None, *, fix: bool = True
    ) -> np.ndarray:
        """Return the internal image buffer.

        **Why Override?** To fix the shape of images with n_components > 1 (like RGB
        images)

        Parameters
        ----------
        numChannel : int, optional
            The camera channel to get the image from.  If None, (the default), then
            Multi-Channel cameras will return the content of the first channel.
        fix : bool, default: True
            If `True` (the default), then images with n_components > 1 (like RGB images)
            will be reshaped to (w, h, n_components) using `fixImage`.
        """
        img = (
            super().getImage(numChannel)
            if numChannel is not None
            else super().getImage()
        )
        return self.fixImage(img) if fix else img

    def startContinuousSequenceAcquisition(self, intervalMs: float = 0) -> None:
        """Start a ContinuousSequenceAcquisition.

        **Why Override?** To emit a `startContinuousSequenceAcquisition` event.
        """
        super().startContinuousSequenceAcquisition(intervalMs)
        self.events.continuousSequenceAcquisitionStarted.emit()

    @overload
    def startSequenceAcquisition(
        self,
        numImages: int,
        intervalMs: float,
        stopOnOverflow: bool,
    ) -> None:
        ...

    @overload
    def startSequenceAcquisition(
        self,
        cameraLabel: str,
        numImages: int,
        intervalMs: float,
        stopOnOverflow: bool,
    ) -> None:
        ...

    def startSequenceAcquisition(self, *args: Any, **kwargs: Any) -> None:
        """Starts streaming camera sequence acquisition.

        This command does not block the calling thread for the duration of the
        acquisition.

        **Why Override?** To emit a `startSequenceAcquisition` event.
        """
        super().startSequenceAcquisition(*args, **kwargs)
        if len(args) == 3:
            numImages, intervalMs, stopOnOverflow = args
            cameraLabel = super().getCameraDevice()
        else:
            cameraLabel, numImages, intervalMs, stopOnOverflow = args
        self.events.sequenceAcquisitionStarted.emit(
            cameraLabel, numImages, intervalMs, stopOnOverflow
        )

    def stopSequenceAcquisition(self, cameraLabel: str | None = None) -> None:
        """Stops streaming camera sequence acquisition.

        (for a specified camera if `cameraLabel` is provided.)

        **Why Override?** To emit a `stopSequenceAcquisition` event.
        """
        if cameraLabel is None:
            super().stopSequenceAcquisition()
        else:
            super().stopSequenceAcquisition(cameraLabel)
        cameraLabel = cameraLabel or super().getCameraDevice()
        self.events.sequenceAcquisitionStopped.emit(cameraLabel)

    def setAutoShutter(self, state: bool) -> None:
        """Set shutter to automatically open and close when an image is acquired.

        **Why Override?** To emit an `autoShutterSet` event.
        """
        super().setAutoShutter(state)
        self.events.autoShutterSet.emit(state)

    @overload
    def setShutterOpen(self, state: bool) -> None:
        ...

    @overload
    def setShutterOpen(self, shutterLabel: str, state: bool) -> None:
        ...

    def setShutterOpen(self, *args: Any, **kwargs: Any) -> None:
        """Open or close the currently selected or `shutterLabel` shutter.

        **Why Override?** To emit a `propertyChanged` event.
        """
        super().setShutterOpen(*args, **kwargs)
        shutterLabel, state = kwargs.get("shutterLabel"), kwargs.get("state")
        if len(args) > 1:
            shutterLabel, state = args
        elif args:
            shutterLabel = super().getShutterDevice()
            state = args
        self.events.propertyChanged.emit(shutterLabel, "State", state)

    @overload
    def deleteConfig(self, groupName: str, configName: str) -> None:
        ...

    @overload
    def deleteConfig(
        self, groupName: str, configName: str, deviceLabel: str, propName: str
    ) -> None:
        ...

    def deleteConfig(
        self,
        groupName: str,
        configName: str,
        deviceLabel: str | None = None,
        propName: str | None = None,
    ) -> None:
        """Delete `configName` from `groupName`.

        **Why Override?** To emit a `configDeleted` event.
        """
        args: tuple[str, ...] = (groupName, configName)
        if deviceLabel is not None and propName is not None:
            args = (*args, deviceLabel, propName)
        super().deleteConfig(*args)
        self.events.configDeleted.emit(groupName, configName)

    def deleteConfigGroup(self, group: str) -> None:
        """Deletes an entire configuration `group`.

        **Why Override?** To emit a `configGroupDeleted` event.
        """
        super().deleteConfigGroup(group)
        self.events.configGroupDeleted.emit(group)

    @overload
    def defineConfig(self, groupName: str, configName: str) -> None:
        ...

    @overload
    def defineConfig(
        self,
        groupName: str,
        configName: str,
        deviceLabel: str,
        propName: str,
        value: str,
    ) -> None:
        ...

    def defineConfig(
        self,
        groupName: str,
        configName: str,
        deviceLabel: str | None = None,
        propName: str | None = None,
        value: str | None = None,
    ) -> None:
        """Defines a configuration.

        **Why Override?** To emit a `configDefined` event.  Also, if `groupName` is
        not a defined group, then `defineConfigGroup(groupName)` is called.
        """
        if not configName:
            idx = sum(UNNAMED_PRESET in p for p in self.getAvailableConfigs(groupName))
            configName = f"{UNNAMED_PRESET}_{idx}" if idx > 0 else UNNAMED_PRESET

        if not self.isGroupDefined(groupName):
            # needed to refresh pymmcore 'ChannelGroup' options
            super().defineConfigGroup(groupName)

        if (deviceLabel is not None) and (propName is not None) and (value is not None):
            super().defineConfig(groupName, configName, deviceLabel, propName, value)
        else:
            deviceLabel, propName, value = ("", "", "")
            super().defineConfig(groupName, configName)

        self.events.configDefined.emit(
            groupName, configName, deviceLabel, propName, value
        )

    def setPixelSizeUm(self, resolutionID: str, pixSize: float) -> None:
        """Set pixel size in microns for the specified `resolutionID`.

        **Why Override?** To emit a `pixelSizeChanged` event.
        """
        super().setPixelSizeUm(resolutionID, pixSize)
        self.events.pixelSizeChanged.emit(pixSize)

    def deletePixelSizeConfig(self, resolutionID: str) -> None:
        """Delete the pixel size configuration for the given `resolutionID`.

        **Why Override?** To emit a `pixelSizeChanged` event.
        """
        super().deletePixelSizeConfig(resolutionID)
        self.events.pixelSizeChanged.emit(0.0)

    @overload
    def definePixelSizeConfig(self, resolutionID: str) -> None:
        ...

    @overload
    def definePixelSizeConfig(
        self, resolutionID: str, deviceLabel: str, propName: str, value: str
    ) -> None:
        ...

    def definePixelSizeConfig(self, *args: str, **kwargs: str) -> None:
        """Defines an empty pixel size entry.

        **Why Override?** To emit a `pixelSizeChanged` event.
        """
        super().definePixelSizeConfig(*args, **kwargs)
        self.events.pixelSizeChanged.emit(0.0)

    @overload
    def setROI(self, x: int, y: int, width: int, height: int) -> None:
        ...

    @overload
    def setROI(self, label: str, x: int, y: int, width: int, height: int) -> None:
        ...

    def setROI(self, *args: Any, **kwargs: Any) -> None:
        """Set the camera Region of Interest (ROI).

        **Why Override?** To emit a `roiSet` event.
        """
        super().setROI(*args, **kwargs)
        if len(args) == 4:
            args = (super().getCameraDevice(), *args)
        self.events.roiSet.emit(*args)

    def setChannelGroup(self, channelGroup: str) -> None:
        """Specifies the group determining the channel selection.

        ...and send a channelGroupChanged signal.
        """
        if self.getChannelGroup() != channelGroup:
            super().setChannelGroup(channelGroup)
            self.events.channelGroupChanged.emit(channelGroup)

    def setFocusDevice(self, focusLabel: str) -> None:
        """Set the current Focus Device and emit a `propertyChanged` signal."""
        if self.getFocusDevice() != focusLabel:
            super().setFocusDevice(focusLabel)
            self.events.propertyChanged.emit("Core", "Focus", focusLabel)

    def saveSystemConfiguration(self, filename: str) -> None:
        """Saves the current system configuration to a text file.

        **Why Override?** To also save pixel size configurations.
        """
        super().saveSystemConfiguration(filename)
        px_configs = self.getAvailablePixelSizeConfigs()
        if not px_configs:
            return
        # saveSystemConfiguration does not save the pixel size config so here
        # we add to the saved file also any pixel size config.
        with open(filename, "a") as f:
            f.write("# PixelSize settings")
            for px_config in px_configs:
                data = self.getPixelSizeConfigData(px_config)
                obj = data.dict()["Objective"]["Label"]
                px_size = self.getPixelSizeUmByID(px_config)
                px_affine = self.getPixelSizeAffineByID(px_config)
                cfg = (
                    f"\nConfigPixelSize,{px_config},Objective,Label,{obj}\n"
                    f"PixelSize_um,{px_config},{px_size}\n"
                    f"PixelSizeAffine,{px_config},{','.join(map(str, px_affine))}"
                )
                f.write(cfg)

    def describe(self, sort: str | None = None) -> None:
        """Print information table with the current configuration.

        Intended to provide a quick overview of the microscope configuration during
        interactive terminal usage.

        :sparkles: *This method is new in `CMMCorePlus`.*
        """
        _current = {
            self.getCameraDevice(): "Camera",
            self.getXYStageDevice(): "XYStage",
            self.getFocusDevice(): "Focus",
            self.getShutterDevice(): "Shutter",
            self.getSLMDevice(): "SLM",
            self.getGalvoDevice(): "Galvo",
            self.getAutoFocusDevice(): "AutoFocus",
            self.getImageProcessorDevice(): "ImageProcessor",
        }

        data: defaultdict[str, list[str]] = defaultdict(list)
        for device in self.iterDevices():
            data["Device Label"].append(device.label)
            data["Type"].append(str(device.type()))
            data["Current"].append(_current.get(device.label, ""))
            data["Library::DeviceName"].append(f"{device.library()}::{device.name()}")
            data["Description"].append(device.description())

        if not any(data["Current"]):
            data.pop("Current")

        print(f"{self.getVersionInfo()}, {self.getAPIVersionInfo()}")
        print("Adapter path:", ",".join(self.getDeviceAdapterSearchPaths()))
        print_tabular_data(data, sort=sort)

    def state(self, exclude: Iterable[str] = ()) -> StateDict:
        """Return `StateDict` with commonly accessed state values.

        :sparkles: *This method is new in `CMMCorePlus`. It is a bit faster
        than [`getSystemState`][pymmcore_plus.CMMCorePlus.getSystemState].*

        Parameters
        ----------
        exclude : Iterable[str]
            List of properties to exclude when gathering state (may speed things up).
            See [`StateDict`][pymmcore_plus.core._mmcore_plus.StateDict] for a list of
            keys that can be excluded.

        Returns
        -------
        StateDict
            A dictionary of commonly accessed state values.
        """
        # approx retrieval cost in comment (for demoCam)
        exclude = set(exclude)
        state: dict = {}
        for attr in (
            "AutoFocusDevice",  # 150 ns
            "BytesPerPixel",  # 149 ns
            "CameraChannelNames",  # 1 µs
            "CameraDevice",  # 159 ns
            "Datetime",
            "Exposure",  # 726 ns
            "FocusDevice",  # 112 ns
            "GalvoDevice",  # 109 ns
            "ImageBitDepth",  # 147 ns
            "ImageHeight",  # 164 ns
            "ImageProcessorDevice",  # 110 ns
            "ImageWidth",  # 172 ns
            "PixelSizeUm",  # 2.2 µs
            "ShutterDevice",  # 152 ns
            "SLMDevice",  # 110 ns
            "XYPosition",  # 1.1 µs
            "XYStageDevice",  # 156 ns
            "ZPosition",  # 1.03 µs
        ):
            if attr not in exclude:
                if attr == "Datetime":
                    state[attr] = str(datetime.now())
                elif attr == "PixelSizeUm":
                    state[attr] = self.getPixelSizeUm(True)  # True==cached
                else:
                    try:
                        state[attr] = getattr(self, f"get{attr}")()
                    except RuntimeError:
                        continue
        return cast("StateDict", state)

    @contextmanager
    def _property_change_emission_ensured(
        self, device: str, properties: Sequence[str]
    ) -> Iterator[None]:
        """Context that emits events if any of `properties` change on device.

        NOTE: Depending on device adapter behavior the signal may be emitted twice.

        Parameters
        ----------
        device : str
            a device label
        properties : Sequence[str]
            a sequence of property names to monitor
        """
        # make sure that changing either state device property emits both signals
        if (
            len(properties) == 1
            and properties[0] in STATE_PROPS
            and self.getDeviceType(device) is DeviceType.StateDevice
        ):
            properties = STATE_PROPS

        before = [self.getProperty(device, p) for p in properties]
        with _blockSignal(self.events, self.events.propertyChanged):
            yield
        after = [self.getProperty(device, p) for p in properties]
        if before != after:
            for i, val in enumerate(after):
                self.events.propertyChanged.emit(device, properties[i], val)

    @contextmanager
    def setContext(self, **kwargs: Any) -> Iterator[None]:
        """Set core properties in a context restoring the initial values on exit.

        :sparkles: *This method is new in `CMMCorePlus`.*

        Parameters
        ----------
        **kwargs : Any
            Keyword arguments may be any `Name` for which `get<Name>` and `set<Name>`
            methods exist.  For example, `setContext(exposure=10)` will call
            `setExposure(10)` when entering the context and `setExposure(<initial>)`
            when exiting the context.

        Examples
        --------
        ```python
        core = CMMCorePlus.instance()

        with core.setContext(autoShutter=False):
            assert not core.getAutoShutter()
            # do other stuff
            ...

        # autoShutter is restored to its original value when the context exits
        assert core.getAutoShutter()
        ```
        """
        orig_values = {}
        try:
            for name, v in kwargs.items():
                name = name[0].upper() + name[1:]
                try:
                    orig_values[name] = getattr(self, f"get{name}")()
                    getattr(self, f"set{name}")(v)
                except AttributeError:
                    logger.warning(f"{name} is not a valid property, skipping.")
            yield
        finally:
            for k, v in orig_values.items():
                with suppress(AttributeError):
                    getattr(self, f"set{k}")(v)

    def canSequenceEvents(
        self, e1: MDAEvent, e2: MDAEvent, cur_length: int = -1
    ) -> bool:
        """Check whether two [`useq.MDAEvent`][] are sequenceable by this core instance.

        Micro-manager calls hardware triggering "sequencing".  Two events can be
        sequenced if *all* device properties that are changing between the first and
        second event support sequencing.

        If `cur_length` is provided, it is used to determine if the sequence is
        "full" (i.e. the sequence is already at the maximum length) as determined by
        the `...SequenceMaxLength()` method corresponding to the device property.

        See: <https://micro-manager.org/Hardware-based_Synchronization_in_Micro-Manager>

        :sparkles: *This method is new in `CMMCorePlus`.*

        Parameters
        ----------
        e1 : MDAEvent
            The first event.
        e2 : MDAEvent
            The second event.
        cur_length : int
            The current length of the sequence.  Used when checking
            `.get<...>SequenceMaxLength` for a given property. If the current length
            is greater than the max length, the events cannot be sequenced. By default
            -1, which means the current length is not checked.

        Returns
        -------
        bool
            True if the events can be sequenced, False otherwise.

        Examples
        --------
        !!! note

            The results here will depend on the current state of the core and devices.

        ```python
        >>> from useq import MDAEvent
        >>> core = CMMCorePlus.instance()
        >>> core.loadSystemConfiguration()
        >>> core.canSequenceEvents(MDAEvent(), MDAEvent())
        True
        >>> core.canSequenceEvents(MDAEvent(x_pos=1), MDAEvent(x_pos=2))
        False
        >>> core.canSequenceEvents(
        ...     MDAEvent(channel={'config': 'DAPI'}),
        ...     MDAEvent(channel={'config': 'FITC'})
        ... )
        False
        ```
        """
        return can_sequence_events(self, e1, e2, cur_length)


for name in (
    "getConfigData",
    "getConfigGroupState",
    "getConfigGroupStateFromCache",
    "getConfigState",
    "getSystemState",
    "getSystemStateCache",
):
    native_doc = getattr(pymmcore.CMMCore, name).__doc__
    getattr(CMMCorePlus, name).__doc__ += (
        "\n"
        + native_doc
        + dedent(
            """
    By default, this method returns a `pymmcore_plus.Configuration` object, which
    provides some conveniences over the native `pymmcore.Configuration` object, however
    this adds a little overhead. Use `native=True` to avoid the conversion.
    """
        ).strip()
    )


class _MMCallbackRelay(pymmcore.MMEventCallback):
    """Relays MMEventCallback methods to CMMCorePlus.signal."""

    def __init__(self, emitter: CMMCoreSignaler):
        self._emitter = emitter
        super().__init__()

    @staticmethod
    def _make_reemitter(name: str) -> Callable[..., None]:
        sig_name = name[2].lower() + name[3:]

        def reemit(self: _MMCallbackRelay, *args: Any) -> None:
            try:
                getattr(self._emitter, sig_name).emit(*args)
            except Exception as e:
                logger.error(
                    f"Exception occured in MMCorePlus callback {sig_name!r}: {e}"
                )

        return reemit


MMCallbackRelay = type(
    "MMCallbackRelay",
    (_MMCallbackRelay,),
    {
        n: _MMCallbackRelay._make_reemitter(n)
        for n in dir(pymmcore.MMEventCallback)
        if n.startswith("on")
    },
)
