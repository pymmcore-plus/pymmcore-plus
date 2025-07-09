from __future__ import annotations

import atexit
import os
import re
import time
import warnings
import weakref
from collections import defaultdict
from contextlib import contextmanager, suppress
from datetime import datetime
from pathlib import Path
from re import Pattern
from textwrap import dedent
from threading import Thread
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    NamedTuple,
    TypeVar,
    cast,
    overload,
)

from psygnal import SignalInstance
from typing_extensions import deprecated

import pymmcore_plus._pymmcore as pymmcore
from pymmcore_plus._logger import current_logfile, logger
from pymmcore_plus._util import find_micromanager, print_tabular_data
from pymmcore_plus.mda import MDAEngine, MDARunner, PMDAEngine
from pymmcore_plus.metadata.functions import summary_metadata

from . import _device
from ._adapter import DeviceAdapter
from ._config import Configuration
from ._config_group import ConfigGroup
from ._constants import (
    DeviceDetectionStatus,
    DeviceInitializationState,
    DeviceType,
    FocusDirection,
    Keyword,
    PixelType,
    PropertyType,
)
from ._metadata import Metadata
from ._property import DeviceProperty
from .events import CMMCoreSignaler, PCoreSignaler, _get_auto_core_callback_class

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence
    from typing import Literal, Never, TypeAlias, TypedDict, Union, Unpack

    import numpy as np
    from pymmcore import DeviceLabel
    from useq import MDAEvent

    from pymmcore_plus.mda._runner import SingleOutput
    from pymmcore_plus.metadata.schema import SummaryMetaV1

    _T = TypeVar("_T")
    _DT = TypeVar("_DT", bound=_device.Device)
    ListOrTuple = list[_T] | tuple[_T, ...]
    DeviceTypesWithCurrent: TypeAlias = Union[
        Literal[DeviceType.CameraDevice]
        | Literal[DeviceType.ShutterDevice]
        | Literal[DeviceType.StageDevice]
        | Literal[DeviceType.XYStageDevice]
        | Literal[DeviceType.AutoFocusDevice]
        | Literal[DeviceType.SLMDevice]
        | Literal[DeviceType.GalvoDevice]
        | Literal[DeviceType.ImageProcessorDevice]
    ]

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

    class SetContextKwargs(TypedDict, total=False):
        """All the valid keywords and their types for the `setContext` method."""

        autoFocusDevice: str
        autoFocusOffset: float
        autoShutter: bool
        cameraDevice: str
        channelGroup: str
        circularBufferMemoryFootprint: int
        deviceAdapterSearchPaths: list[str]
        deviceDelayMs: tuple[str, float]
        exposure: float | tuple[str, float]
        focusDevice: str
        focusDirection: str
        galvoDevice: str
        galvoPosition: tuple[str, float, float]
        imageProcessorDevice: str
        multiROI: tuple[list[int], list[int], list[int], list[int]]
        parentLabel: tuple[str, str]
        pixelSizeAffine: tuple[str, list[float]]
        pixelSizeUm: tuple[str, float]
        position: float | tuple[str, float]
        primaryLogFile: str | tuple[str, bool]
        property: tuple[str, str, bool | float | int | str]
        ROI: tuple[int, int, int, int] | tuple[str, int, int, int, int]
        SLMDevice: str
        SLMExposure: tuple[str, float]
        shutterDevice: str
        shutterOpen: bool | tuple[str, bool]
        state: tuple[str, int]
        stateLabel: tuple[str, str]
        systemState: pymmcore.Configuration
        timeoutMs: int
        XYPosition: tuple[float, float] | tuple[str, float, float]
        XYStageDevice: str
        ZPosition: float | tuple[str, float]


_OBJDEV_REGEX = re.compile("(.+)?(nosepiece|obj(ective)?)(turret)?s?", re.IGNORECASE)
_CHANNEL_REGEX = re.compile("(chan{1,2}(el)?|filt(er)?)s?", re.IGNORECASE)

# these are devices for which setAutoFocusOffset is known to have no effect
# maps (device_library, device_name) -> offset_device_name
# see _getAutoFocusOffsetDevice for details
_OFFSET_DEVICES: dict[tuple[str, str], str] = {
    ("NikonTE2000", "PerfectFocus"): "PFS-Offset",
    ("NikonTI", "TIPFSStatus"): "TIPFSOffset",
    # --------------------------
    # these devices have an apparent offset device
    # but may implicitly/privately control it just fine with the setOffset API
    # need testing to see whether setAutoFocusOffset works as is.
    # ("ZeissCAN29", "ZeissDefiniteFocus"): "ZeissDefiniteFocusOffset",
    # ("Olympus", "AutoFocusZDC"): "ZDC2OffsetDrive",
    # ("OlympusIX83", "Autofocus"): "AutofocusDrive",
    # ("LeicaDMI", "Adaptive Focus Control"): "Adaptive Focus Control Offset",
    # --------------------------
    # these devices have a known no-op for setOffset()
    # but have no apparent offset device
    # ("DemoCamera", "DAutoFocus"): "",
    # ("AmScope", ""): "",
    # ("ASIStage", "CRIF"): "",
    # ("FocalPoint", "FocalPoint"): "",
}

STATE = pymmcore.g_Keyword_State
LABEL = pymmcore.g_Keyword_Label
STATE_PROPS = (STATE, LABEL)
UNNAMED_PRESET = "NewPreset"


class TaggedImage(NamedTuple):
    pix: np.ndarray
    tags: dict[str, Any]


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
        if os.getenv("PYMM_DEBUG_LOG", "0").lower() in ("1", "true"):
            self.enableDebugLog(True)
        if os.getenv("PYMM_STDERR_LOG", "0").lower() in ("1", "true"):
            self.enableStderrLog(True)
        if buf_size := os.getenv("PYMM_BUFFER_SIZE_MB", ""):
            try:
                buf_size_int = int(buf_size)
                if buf_size_int:
                    self.setCircularBufferMemoryFootprint(buf_size_int)
            except (ValueError, TypeError):
                warnings.warn("PYMM_BUFFER_SIZE_MB must be an integer", stacklevel=2)

        # Set the first instance of this class as the global singleton
        global _instance
        if _instance is None:
            _instance = self

        if hasattr(self, "enableFeature"):
            strict = True
            if env_strict := os.getenv("PYMM_STRICT_INIT_CHECKS", "").lower():
                if env_strict in ("1", "true"):
                    strict = True
                elif env_strict in ("0", "false"):
                    strict = False
            self.enableFeature("StrictInitializationChecks", strict)

            parallel = True
            if env_parallel := os.getenv("PYMM_PARALLEL_INIT", "").lower():
                if env_parallel in ("1", "true"):
                    parallel = True
                elif env_parallel in ("0", "false"):
                    parallel = False
            self.enableFeature("ParallelDeviceInitialization", parallel)

        # TODO: test this on windows ... writing to the same file may be an issue there
        if logfile := current_logfile(logger):
            self.setPrimaryLogFile(str(logfile))
            logger.debug("Initialized core %s", self)

        # some internal state, remembering the last arguments passed to various
        # functions.  These are subject to change: do not depend on externally
        self._last_sys_config: str | None = None  # last loaded config file
        self._last_config: tuple[str, str] = ("", "")
        # last position set by setXYPosition, None means currentXYStageDevice
        self._last_xy_position: dict[str | None, tuple[float, float]] = {}

        self._mm_path = mm_path or find_micromanager()
        if not adapter_paths and self._mm_path:
            adapter_paths = [self._mm_path]
        if adapter_paths:
            self.setDeviceAdapterSearchPaths(adapter_paths)

        self._events = _get_auto_core_callback_class()()
        self._callback_relay = MMCallbackRelay(self.events)
        super().registerCallback(self._callback_relay)

        self._mda_runner = MDARunner()
        self._mda_runner.set_engine(MDAEngine(self))

        self._objective_regex: Pattern = _OBJDEV_REGEX
        self._channel_group_regex: Pattern = _CHANNEL_REGEX

        # use weakref to avoid atexit keeping us from being
        # garbage collected
        self._weak_clean = weakref.WeakMethod(self.unloadAllDevices)
        atexit.register(self._weak_clean)

    @deprecated(
        "registerCallback is disallowed in pymmcore-plus.  Use .events instead."
    )
    def registerCallback(self, *_: Never) -> Never:  # type: ignore[override]
        """*registerCallback is disallowed in pymmcore-plus!*

        If you want to connect callbacks to events, use the
        [`CMMCorePlus.events`][pymmcore_plus.CMMCorePlus.events] property instead.
        """  # noqa
        raise RuntimeError(
            dedent("""
            This method is disallowed in pymmcore-plus.

            If you want to connect callbacks to events, use the
            `CMMCorePlus.events` property instead.
            """)
        )

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
        """Return a string representation of the core object."""
        ndevices = len(self.getLoadedDevices()) - 1
        return f"<{type(self).__name__} at {hex(id(self))} with {ndevices} devices>"

    def __del__(self) -> None:
        if hasattr(self, "_weak_clean"):
            atexit.unregister(self._weak_clean)
        try:
            super().registerCallback(None)
            self.reset()
            # clean up logging
            self.setPrimaryLogFile("")
        except Exception as e:
            logger.exception("Error during CMMCorePlus.__del__(): %s", e)

    # Re-implemented methods from the CMMCore API

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

    def setStateLabel(self, stateDeviceLabel: str, stateLabel: str) -> None:
        """Set state (by label) on `stateDeviceLabel`, with reliable event emission.

        **Why Override?**  In `MMCore`, the calling of the `onPropertyChanged`
        callback is left to the underlying device adapter, which means it is not always
        called.  This method overrides the default implementation to ensure that
        `events.propertyChanged` is *always* emitted when `setProperty` has been called
        and the property Value has actually changed.
        """
        with self._property_change_emission_ensured(stateDeviceLabel, STATE_PROPS):
            try:
                super().setStateLabel(stateDeviceLabel, stateLabel)
            except RuntimeError as e:  # pragma: no cover
                state_labels = self.getStateLabels(stateDeviceLabel)
                msg = f"{e}.  Available Labels: {state_labels}"
                raise RuntimeError(msg) from None

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
        logger.debug("setting adapter search paths: %s", paths)
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
        if str(label).lower() == Keyword.CoreDevice.value.lower():  # pragma: no cover
            raise ValueError(f"Label {label!r} is reserved.")

        try:
            super().loadDevice(label, moduleName, deviceName)
        except (RuntimeError, ValueError) as e:
            if exc := self._load_error_with_info(label, moduleName, deviceName, str(e)):
                raise exc from e

    def _load_error_with_info(
        self, label: str, moduleName: str, deviceName: str, msg: str = ""
    ) -> RuntimeError | None:
        if label in self.getLoadedDevices():
            lib = super().getDeviceLibrary(label)
            name = super().getDeviceName(label)
            if moduleName == lib and deviceName == name:
                msg += f". Device {label!r} appears to be loaded already."
                warnings.warn(msg, stacklevel=2)
                return None

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
        return RuntimeError(msg)

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
        self._last_sys_config = str(fpath.resolve())
        super().loadSystemConfiguration(self._last_sys_config)

    def systemConfigurationFile(self) -> str | None:
        """Return the path to the last loaded system configuration file, or `None`.

        :sparkles: *This method is new in `CMMCorePlus`.*
        """
        return self._last_sys_config

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

    def getFocusDirection(self, stageLabel: str) -> FocusDirection:
        """Return device type for a given device.

        **Why Override?** The returned [`pymmcore_plus.FocusDirection`][] enum is more
        interpretable than the raw `int` returned by `pymmcore`
        """
        return FocusDirection(super().getFocusDirection(stageLabel))

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

    def getDeviceInitializationState(self, label: str) -> DeviceInitializationState:
        """Queries the initialization state of the given device.

        **Why Override?** The returned [`pymmcore_plus.DeviceInitializationState`][]
        enum is more interpretable than the raw `int` returned by `pymmcore`
        """
        return DeviceInitializationState(super().getDeviceInitializationState(label))

    # config overrides

    @overload
    def getConfigData(
        self, configGroup: str, configName: str, *, native: Literal[True]
    ) -> pymmcore.Configuration: ...

    @overload
    def getConfigData(
        self, configGroup: str, configName: str, *, native: Literal[False] = False
    ) -> Configuration: ...

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
    ) -> pymmcore.Configuration: ...

    @overload
    def getPixelSizeConfigData(
        self, configName: str, *, native: Literal[False] = False
    ) -> Configuration: ...

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
    ) -> pymmcore.Configuration: ...

    @overload
    def getConfigGroupState(
        self, group: str, *, native: Literal[False] = False
    ) -> Configuration: ...

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

    @overload
    def getConfigGroupStateFromCache(
        self, group: str, *, native: Literal[True]
    ) -> pymmcore.Configuration: ...

    @overload
    def getConfigGroupStateFromCache(
        self, group: str, *, native: Literal[False] = False
    ) -> Configuration: ...

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

    @overload
    def getSystemStateCache(
        self, *, native: Literal[True]
    ) -> pymmcore.Configuration: ...

    @overload
    def getSystemStateCache(
        self, *, native: Literal[False] = False
    ) -> Configuration: ...

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
    ) -> tuple[np.ndarray, Metadata]: ...

    @overload
    def getLastImageAndMD(self, *, fix: bool = True) -> tuple[np.ndarray, Metadata]: ...

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
            img = self.getLastImageMD(channel, slice, md)
        else:
            img = self.getLastImageMD(md)
        return (self.fixImage(img) if fix and not pymmcore.NANO else img, md)

    @overload
    def popNextImageAndMD(
        self, channel: int, slice: int, *, fix: bool = True
    ) -> tuple[np.ndarray, Metadata]: ...

    @overload
    def popNextImageAndMD(self, *, fix: bool = True) -> tuple[np.ndarray, Metadata]: ...

    def popNextImageAndMD(
        self, channel: int = 0, slice: int = 0, *, fix: bool = True
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
        img = self.popNextImageMD(channel, slice, md)
        return (self.fixImage(img) if fix and not pymmcore.NANO else img, md)

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
        return self.fixImage(img) if fix and not pymmcore.NANO else img

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
        img = self.getNBeforeLastImageMD(n, md)
        return self.fixImage(img) if fix and not pymmcore.NANO else img, md

    def setConfig(self, groupName: str, configName: str) -> None:
        """Applies a configuration to a group.

        **Why Override?** The native `onConfigGroupChanged` callback is not always
        called whenever `CMMCore.setConfig` has been called. We override here to emit
        a `configSet` event whenever `setConfig` is called.
        See <https://github.com/micro-manager/mmCoreAndDevices/issues/25> for details.
        """
        super().setConfig(groupName, configName)
        self.events.configSet.emit(groupName, configName)
        self._last_config = (groupName, configName)

    # NEW methods

    @overload
    def iterDeviceAdapters(
        self,
        adapter_pattern: str | re.Pattern | None = ...,
        *,
        as_object: Literal[True] = ...,
    ) -> Iterator[DeviceAdapter]: ...

    @overload
    def iterDeviceAdapters(
        self,
        adapter_pattern: str | re.Pattern | None = ...,
        *,
        as_object: Literal[False],
    ) -> Iterator[str]: ...

    def iterDeviceAdapters(
        self,
        adapter_pattern: str | re.Pattern | None = None,
        *,
        as_object: bool = True,
    ) -> Iterator[DeviceAdapter] | Iterator[str]:
        """Iterate over all available device adapters.

        :sparkles: *This method is new in `CMMCorePlus`.*

        It offers a convenient way to iterate over available device adaptor libraries,
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
    ) -> Iterator[str]: ...

    @overload
    def iterDevices(
        self,
        device_type: int | Iterable[int] | None = ...,
        device_label: str | re.Pattern | None = ...,
        device_adapter: str | re.Pattern | None = ...,
        *,
        as_object: Literal[True] = ...,
    ) -> Iterator[_device.Device]: ...

    def iterDevices(
        self,
        device_type: int | Iterable[int] | None = None,
        device_label: str | re.Pattern | None = None,
        device_adapter: str | re.Pattern | None = None,
        *,
        as_object: bool = True,
    ) -> Iterator[_device.Device] | Iterator[str]:
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
            yield _device.Device.create(dev, mmcore=self) if as_object else dev

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
    ) -> Iterator[tuple[str, str]]: ...

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
    ) -> Iterator[DeviceProperty]: ...

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

        get/set property values easily:

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

    @overload
    def getDeviceObject(
        self, device_label: str, device_type: Literal[DeviceType.Camera]
    ) -> _device.CameraDevice: ...
    @overload
    def getDeviceObject(
        self, device_label: str, device_type: Literal[DeviceType.Stage]
    ) -> _device.StageDevice: ...
    @overload
    def getDeviceObject(
        self, device_label: str, device_type: Literal[DeviceType.State]
    ) -> _device.StateDevice: ...
    @overload
    def getDeviceObject(
        self, device_label: str, device_type: Literal[DeviceType.Shutter]
    ) -> _device.ShutterDevice: ...
    @overload
    def getDeviceObject(
        self, device_label: str, device_type: Literal[DeviceType.XYStage]
    ) -> _device.XYStageDevice: ...
    @overload
    def getDeviceObject(
        self, device_label: str, device_type: Literal[DeviceType.Serial]
    ) -> _device.SerialDevice: ...
    @overload
    def getDeviceObject(
        self, device_label: str, device_type: Literal[DeviceType.Generic]
    ) -> _device.GenericDevice: ...
    @overload
    def getDeviceObject(
        self, device_label: str, device_type: Literal[DeviceType.AutoFocus]
    ) -> _device.AutoFocusDevice: ...
    @overload
    def getDeviceObject(
        self, device_label: str, device_type: Literal[DeviceType.ImageProcessor]
    ) -> _device.ImageProcessorDevice: ...
    @overload
    def getDeviceObject(
        self, device_label: str, device_type: Literal[DeviceType.SignalIO]
    ) -> _device.SignalIODevice: ...
    @overload
    def getDeviceObject(
        self, device_label: str, device_type: Literal[DeviceType.Magnifier]
    ) -> _device.MagnifierDevice: ...
    @overload
    def getDeviceObject(
        self, device_label: str, device_type: Literal[DeviceType.SLM]
    ) -> _device.SLMDevice: ...
    @overload
    def getDeviceObject(
        self, device_label: str, device_type: Literal[DeviceType.Hub]
    ) -> _device.HubDevice: ...
    @overload
    def getDeviceObject(
        self, device_label: str, device_type: Literal[DeviceType.Galvo]
    ) -> _device.GalvoDevice: ...
    @overload
    def getDeviceObject(
        self,
        device_label: Literal[Keyword.CoreDevice],
        device_type: Literal[DeviceType.Core],
    ) -> _device.CoreDevice: ...
    @overload
    def getDeviceObject(
        self, device_label: str, device_type: DeviceType = ...
    ) -> _device.Device: ...
    @overload
    def getDeviceObject(self, device_label: str, device_type: type[_DT]) -> _DT: ...
    def getDeviceObject(
        self, device_label: str, device_type: type[_DT] | DeviceType = DeviceType.Any
    ) -> _DT | _device.Device:
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
        dev = _device.Device.create(device_label, mmcore=self)
        if (isinstance(device_type, type) and not isinstance(dev, device_type)) or (
            isinstance(device_type, DeviceType)
            and device_type not in {DeviceType.Any, DeviceType.Unknown}
            and dev.type() != device_type
        ):
            raise TypeError(
                f"{device_type!r} requested but device with label "
                f"{device_label!r} is a {dev.type()}."
            )

        return dev

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
        allow_missing : bool
            If `False` and the `ConfigGroup` does not exist, a `KeyError` will be
            raised. By default False.


        Returns
        -------
        ConfigGroup
            [`ConfigGroup`][pymmcore_plus.ConfigGroup] object bound to `group_name`
            on this core.
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

    def getCurrentDeviceOfType(
        self, device_type: DeviceTypesWithCurrent
    ) -> DeviceLabel | Literal[""]:
        """Return the current device of type `device_type`.

        Only the following device types have a "current" device:
            - CameraDevice
            - ShutterDevice
            - StageDevice
            - XYStageDevice
            - AutoFocusDevice
            - SLMDevice
            - GalvoDevice
            - ImageProcessorDevice

        Calling this method with any other device type will raise a `ValueError`.

        :sparkles: *This method is new in `CMMCorePlus`.*

        Parameters
        ----------
        device_type : DeviceType
            The type of device to get the current device for.
            See [`DeviceType`][pymmcore_plus.DeviceType] for a list of device types.

        Returns
        -------
        str
            The label of the current device of type `device_type`.
            If no device of that type is currently set, an empty string is returned.

        Raises
        ------
        ValueError
            If the core does not have the concept of a "current" device of the provided
            `device_type`.
        """
        if device_type == DeviceType.CameraDevice:
            return self.getCameraDevice()
        if device_type == DeviceType.ShutterDevice:
            return self.getShutterDevice()
        if device_type == DeviceType.StageDevice:
            return self.getFocusDevice()
        if device_type == DeviceType.XYStageDevice:
            return self.getXYStageDevice()
        if device_type == DeviceType.AutoFocusDevice:
            return self.getAutoFocusDevice()
        if device_type == DeviceType.SLMDevice:
            return self.getSLMDevice()
        if device_type == DeviceType.GalvoDevice:
            return self.getGalvoDevice()
        if device_type == DeviceType.ImageProcessorDevice:
            return self.getImageProcessorDevice()
        raise ValueError(f"'Current' {device_type.name} is undefined. ")

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

    @overload
    def setXYPosition(self, x: float, y: float, /) -> None: ...
    @overload
    def setXYPosition(self, xyStageLabel: str, x: float, y: float, /) -> None: ...
    def setXYPosition(self, *args: Any) -> None:
        """Sets the position of the XY stage in microns.

        **Why Override?** to store the last commanded stage position internally.
        """
        if len(args) == 2:
            label: str | None = None
            x, y = cast("tuple[float, float]", args)
        elif len(args) == 3:
            label, x, y = args
        else:
            raise ValueError("Invalid number of arguments. Expected 2 or 3.")
        super().setXYPosition(*args)
        self._last_xy_position[label] = (x, y)

    def getZPosition(self) -> float:
        """Obtains the current position of the Z axis of the Z stage in microns.

        :sparkles: *This method is new in `CMMCorePlus`:
        added to complement `getXPosition` and `getYPosition`*

        !!! note
            This is simply an alias for `getPosition`], which returns the position of
            the current focus device when called without arguments.
        """
        return self.getPosition()

    def setZPosition(self, val: float) -> None:
        """Set the position of the current focus device in microns.

        :sparkles: *This method is new in `CMMCorePlus`:
        added to complement `setXYPosition`*

        !!! note
            This is simply an alias for `setPosition`, which returns the position of the
            current focus device when called with a single argument.
        """
        return self.setPosition(val)

    def getCameraChannelNames(self) -> tuple[str, ...]:
        """Convenience method to call `getCameraChannelName` for all camera channels.

        :sparkles: *This method is new in `CMMCorePlus`.*
        """
        return tuple(
            self.getCameraChannelName(i)
            for i in range(self.getNumberOfCameraChannels())
        )

    def snapImage(self) -> None:
        """Acquires a single image with current settings.

        **Why Override?** to emit the `imageSnapped` event after snapping an image.
        and to emit shutter property changes if `getAutoShutter` is `True`.
        """
        if autoshutter := self.getAutoShutter():
            self.events.propertyChanged.emit(self.getShutterDevice(), "State", True)
        try:
            self._do_snap_image()
            self.events.imageSnapped.emit(self.getCameraDevice())
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

    def run_mda(
        self,
        events: Iterable[MDAEvent],
        *,
        output: SingleOutput | Sequence[SingleOutput] | None = None,
        block: bool = False,
    ) -> Thread:
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
        output : SingleOutput | Sequence[SingleOutput] | None, optional
            The output handler(s) to use.  If None, no output will be saved.
            "SingleOutput" can be any of the following:

            - A string or Path to a directory to save images to. A handler will be
                created automatically based on the extension of the path.
            - A handler object that implements the `DataHandler` protocol, currently
                meaning it has a `frameReady` method.  See `mda_listeners_connected`
                for more details.
            - A sequence of either of the above. (all will be connected)
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
        th = Thread(target=self.mda.run, args=(events,), kwargs={"output": output})
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

    def fixImage(
        self,
        img: np.ndarray,
        ncomponents: int | None = None,
    ) -> np.ndarray:
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
        if ncomponents == 4 and img.ndim != 3:
            new_shape = (*img.shape, 4)
            img = img.view(dtype=f"u{img.dtype.itemsize // 4}").reshape(new_shape)
            img = img[..., [2, 1, 0]]  # Convert from BGRA to RGB
        return img

    def getPhysicalCameraDevice(self, channel_index: int = 0) -> str:
        """Return the name of the actual camera device for a given channel index.

        :sparkles: *This method is new in `CMMCorePlus`.* It provides a convenience
        for accessing the name of the actual camera device when using the multi-camera
        utility.
        """
        cam_dev = self.getCameraDevice()
        # best as I can tell, this is a hard-coded string in Utilities/MultiCamera.cpp
        # (it also appears in ArduinoCounter.cpp).  This appears to be "the way"
        # to get at the original camera when using the multi-camera utility.
        prop_name = f"Physical Camera {channel_index + 1}"
        if self.hasProperty(cam_dev, prop_name):
            return self.getProperty(cam_dev, prop_name)
        if channel_index > 0:
            warnings.warn(
                f"Camera {cam_dev} does not have a property {prop_name}. "
                f"Cannot get channel_index={channel_index}",
                stacklevel=2,
            )
        return cam_dev

    def getTaggedImage(self, channel_index: int = 0) -> TaggedImage:
        """Return getImage as named tuple with metadata.

        :sparkles: *This method is new in `CMMCorePlus`.* It returns an object
        similar to MMCoreJ.getTaggedImage().
        """
        img = self.getImage(channel_index)
        return TaggedImage(img, self.getTags(None, channel_index))

    def popNextTaggedImage(self, channel_index: int = 0) -> TaggedImage:
        """Return popNextImageAndMD as named tuple with metadata.

        :sparkles: *This method is new in `CMMCorePlus`.* It returns an object
        similar to MMCoreJ.popNextTaggedImage().
        """
        img, meta = self.popNextImageAndMD(channel_index, 0)
        return TaggedImage(img, self.getTags(meta, channel_index))

    # this matches the MMCoreJ implementation ... which we may or may not want to do?
    def getTags(
        self, meta: Metadata | None = None, channel_index: int | None = None
    ) -> dict[str, Any]:
        """Return a dict of metadata tags for the state of the core.

        NOTE: this function is pretty slow, and is potentially called on every frame
        of an acquisition. It would be nice to determine what is absolutely necessary,
        and possible allow the user to specify what they want to include.

        :sparkles: *This method is new in `CMMCorePlus`.* It returns only the `.tags`
        attribute of what you would get with `getTaggedImage()` or
        `popNextTaggedImage()`.
        """
        # TODO: make these keys into an enum or something somewhere...
        # you shouldn't have to search the code to find out what keys are available

        tags = dict(meta) if meta else {}
        for dev, label, val in self.getSystemStateCache():
            tags[f"{dev}-{label}"] = val

        tags["BitDepth"] = self.getImageBitDepth()

        # NOTE: AcqEngJ appears to also add this as PixelSize_um
        # while MMCoreJ uses PixelSizeUm?  not sure why both are needed
        tags["PixelSizeUm"] = self.getPixelSizeUm(True)  # true == cached

        affine = self.getPixelSizeAffine(True)  # true == cached
        tags["PixelSizeAffine"] = ";".join(str(x) for x in affine)
        tags["ROI"] = "-".join(str(x) for x in self.getROI())
        tags["Width"] = self.getImageWidth()
        tags["Height"] = self.getImageHeight()
        tags["PixelType"] = str(
            PixelType.for_bytes(self.getBytesPerPixel(), self.getNumberOfComponents())
        )
        tags["Frame"] = 0
        tags["FrameIndex"] = 0
        tags["Position"] = "Default"
        tags["PositionIndex"] = 0
        tags["Slice"] = 0
        tags["SliceIndex"] = 0

        try:
            channel_group = self.getPropertyFromCache("Core", "ChannelGroup")
            channel: str = self.getCurrentConfigFromCache(channel_group)
        except Exception:
            channel = "Default"
        tags["Channel"] = channel
        tags["ChannelIndex"] = 0

        with suppress(Exception):
            tags["Binning"] = self.getProperty(self.getCameraDevice(), "Binning")

        if channel_index is not None:
            tags["CameraChannelIndex"] = channel_index
            tags["ChannelIndex"] = channel_index
            tags["Camera"] = self.getPhysicalCameraDevice(channel_index)

        # these are added by AcqEngJ
        # yyyy-MM-dd HH:mm:ss.mmmmmm  # NOTE AcqEngJ omits microseconds
        tags["Time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

        # used by Runner
        tags["PerfCounter"] = time.perf_counter()
        return tags

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
        return img

    @overload
    def getImage(self, *, fix: bool = True) -> np.ndarray:  # noqa: D418
        """Return the internal image buffer."""

    @overload
    def getImage(self, numChannel: int, *, fix: bool = True) -> np.ndarray:  # noqa
        """Return the internal image buffer for a given Camera Channel."""

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
        return self.fixImage(img) if fix and not pymmcore.NANO else img

    def startContinuousSequenceAcquisition(self, intervalMs: float = 0) -> None:
        """Start a ContinuousSequenceAcquisition.

        **Why Override?** To emit a `startContinuousSequenceAcquisition` event.
        """
        self.events.continuousSequenceAcquisitionStarting.emit()
        self._do_start_continuous_sequence_acquisition(intervalMs)
        self.events.continuousSequenceAcquisitionStarted.emit()

    @overload
    def startSequenceAcquisition(
        self, numImages: int, intervalMs: float, stopOnOverflow: bool, /
    ) -> None: ...

    @overload
    def startSequenceAcquisition(
        self,
        cameraLabel: str,
        numImages: int,
        intervalMs: float,
        stopOnOverflow: bool,
        /,
    ) -> None: ...

    def startSequenceAcquisition(self, *args: Any) -> None:
        """Starts streaming camera sequence acquisition.

        This command does not block the calling thread for the duration of the
        acquisition.

        **Why Override?** To emit a `startSequenceAcquisition` event.
        """
        if len(args) == 3:
            args = (self.getCameraDevice(), *args)
        elif len(args) != 4:
            raise ValueError(
                "startSequenceAcquisition requires either 3 or 4 arguments, "
                f"got {len(args)}."
            )

        self.events.sequenceAcquisitionStarting.emit(*args)
        self._do_start_sequence_acquisition(*args)
        self.events.sequenceAcquisitionStarted.emit(*args)

    def stopSequenceAcquisition(self, cameraLabel: str | None = None) -> None:
        """Stops streaming camera sequence acquisition.

        (for a specified camera if `cameraLabel` is provided.)

        **Why Override?** To emit a `stopSequenceAcquisition` event.
        """
        cameraLabel = cameraLabel or super().getCameraDevice()
        self._do_stop_sequence_acquisition(cameraLabel)
        self.events.sequenceAcquisitionStopped.emit(cameraLabel)

    # here for ease of overriding in Unicore ---------------------

    def _do_snap_image(self) -> None:
        super().snapImage()

    def _do_start_sequence_acquisition(
        self, cameraLabel: str, numImages: int, intervalMs: float, stopOnOverflow: bool
    ) -> None:
        super().startSequenceAcquisition(
            cameraLabel, numImages, intervalMs, stopOnOverflow
        )

    def _do_start_continuous_sequence_acquisition(self, intervalMs: float) -> None:
        """Starts the actual continuous sequence acquisition process."""
        super().startContinuousSequenceAcquisition(intervalMs)

    def _do_stop_sequence_acquisition(self, cameraLabel: str) -> None:
        """Stops the actual sequence acquisition process."""
        super().stopSequenceAcquisition(cameraLabel)

    # end of Unicore helpers ---------------------

    def setAutoFocusOffset(self, offset: float) -> None:
        """Applies offset the one-shot focusing device.

        In micro-manager, there is some variability in the way that autofocus devices
        are implemented.  Some have a separate offset device, while others can directly
        set the offset of an associated device.  As a result, calling
        `setAutoFocusOffset`, may or may not do anything depending on the current
        autofocus device.

        This method attempts to detect known autofocus devices and
        """
        if offset_dev := self._getAutoFocusOffsetDevice():
            self.setPosition(offset_dev, offset)
        super().setAutoFocusOffset(offset)

    def getAutoFocusOffset(self) -> float:
        if offset_dev := self._getAutoFocusOffsetDevice():
            return self.getPosition(offset_dev)
        return super().getAutoFocusOffset()

    def _getAutoFocusOffsetDevice(self, af_dev: str | None = None) -> str | None:
        """Return label of offset device for `af_dev` or the current autofocus device.

        This method matches the device library and name of the provided or autofocus
        device against a list of known autofocus devices that have an offset device
        that must be manually managed.  If a match is found, the label of a currently
        loaded stage device is returned (which may be used in a call to `setPosition`).

        If no match is found, `None` is returned.
        """
        if af_dev is None:
            af_dev = self.getAutoFocusDevice()

        if af_dev:
            try:
                lib_name = self.getDeviceLibrary(af_dev)
            except RuntimeError:
                return None
            dev_name = self.getDeviceName(af_dev)
            if offset_dev := _OFFSET_DEVICES.get((lib_name, dev_name)):
                # a match was found,
                # find the label of currently loaded device with the same name
                for dev in self.getLoadedDevicesOfType(DeviceType.StageDevice):
                    if self.getDeviceName(dev) == offset_dev:
                        return dev
        return None

    def setAutoShutter(self, state: bool) -> None:
        """Set shutter to automatically open and close when an image is acquired.

        **Why Override?** To emit an `autoShutterSet` event.
        """
        super().setAutoShutter(state)
        self.events.autoShutterSet.emit(state)

    @overload
    def setShutterOpen(self, state: bool, /) -> None: ...
    @overload
    def setShutterOpen(self, shutterLabel: str, state: bool, /) -> None: ...
    def setShutterOpen(self, *args: Any) -> None:
        """Open or close the currently selected or `shutterLabel` shutter.

        **Why Override?** To emit a `propertyChanged` event.
        """
        if len(args) == 2:
            shutterLabel, state = args
        elif len(args) == 1:
            shutterLabel = super().getShutterDevice()
            state = args[0]
        self._do_shutter_open(shutterLabel, state)
        state = str(int(bool(state)))
        self.events.propertyChanged.emit(shutterLabel, "State", state)

    def _do_shutter_open(self, shutterLabel: str, state: bool, /) -> None:
        """Open or close the shutter."""
        super().setShutterOpen(shutterLabel, state)

    @overload
    def deleteConfig(self, groupName: str, configName: str) -> None: ...

    @overload
    def deleteConfig(
        self, groupName: str, configName: str, deviceLabel: str, propName: str
    ) -> None: ...

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
    def defineConfig(self, groupName: str, configName: str) -> None: ...

    @overload
    def defineConfig(
        self,
        groupName: str,
        configName: str,
        deviceLabel: str,
        propName: str,
        value: str,
    ) -> None: ...

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
    def definePixelSizeConfig(self, resolutionID: str) -> None: ...

    @overload
    def definePixelSizeConfig(
        self, resolutionID: str, deviceLabel: str, propName: str, value: str
    ) -> None: ...

    def definePixelSizeConfig(self, *args: str, **kwargs: str) -> None:
        """Defines an empty pixel size entry.

        **Why Override?** To emit a `pixelSizeChanged` event.
        """
        super().definePixelSizeConfig(*args, **kwargs)
        self.events.pixelSizeChanged.emit(0.0)

    # pymmcore-SWIG needs this, but pymmcore-nano doesn't
    if hasattr(pymmcore, "UnsignedVector"):

        def getMultiROI(  # type: ignore [override]
            self, *_: Any
        ) -> tuple[list[int], list[int], list[int], list[int]]:
            """Get multiple ROIs from the current camera device.

            Will fail if the camera does not support multiple ROIs. Will return empty
            vectors if multiple ROIs are not currently being used.

            **Why Override?** So that the user doesn't need to pass in four empty
            pymmcore.UnsignedVector() objects.
            """
            if _:
                warnings.warn(  # pragma: no cover
                    "Unlike pymmcore, CMMCorePlus.getMultiROI does not require "
                    "arguments. Arguments are ignored.",
                    stacklevel=2,
                )

            xs = pymmcore.UnsignedVector()  # type: ignore [attr-defined]
            ys = pymmcore.UnsignedVector()  # type: ignore [attr-defined]
            ws = pymmcore.UnsignedVector()  # type: ignore [attr-defined]
            hs = pymmcore.UnsignedVector()  # type: ignore [attr-defined]
            super().getMultiROI(xs, ys, ws, hs)
            return list(xs), list(ys), list(ws), list(hs)

    @overload
    def setROI(self, x: int, y: int, width: int, height: int, /) -> None: ...

    @overload
    def setROI(
        self, label: str, x: int, y: int, width: int, height: int, /
    ) -> None: ...

    def setROI(self, *args: Any) -> None:
        """Set the camera Region of Interest (ROI).

        **Why Override?** To emit a `roiSet` event.
        """
        if len(args) == 4:
            args = (super().getCameraDevice(), *args)
        self._do_set_roi(*args)
        self.events.roiSet.emit(*args)

    # here for ease of overriding in Unicore

    def _do_set_roi(self, label: str, x: int, y: int, width: int, height: int) -> None:
        """Internal method to set the ROI for a specific camera device."""
        super().setROI(label, x, y, width, height)

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
        if pymmcore.version_info < (11, 5):
            # saveSystemConfiguration does not save the pixel size config so hereq
            # we add to the saved file also any pixel size config.
            self._save_pixel_configurations(filename)

    def _save_pixel_configurations(self, filename: str) -> None:
        px_configs = self.getAvailablePixelSizeConfigs()
        if not px_configs:
            return
        cfg = ["# PixelSize settings"]
        for px_config in px_configs:
            cfg.extend(
                f"ConfigPixelSize,{px_config},{device},{prop},{val}"
                for device, prop, val in self.getPixelSizeConfigData(px_config)
            )
            px_size = self.getPixelSizeUmByID(px_config)
            px_affine = self.getPixelSizeAffineByID(px_config)
            cfg.extend(
                (
                    f"PixelSize_um,{px_config},{px_size}",
                    f"PixelSizeAffine,{px_config},{','.join(map(str, px_affine))}",
                )
            )
        with open(filename, "a") as f:
            f.write("\n".join(cfg))

    def describe(
        self,
        sort: str | None = None,
        show_config_groups: bool = False,
        show_available: bool = False,
    ) -> None:
        """Print information table with the current configuration.

        Intended to provide a quick overview of the microscope configuration during
        interactive terminal usage.

        :sparkles: *This method is new in `CMMCorePlus`.*
        """
        _current: dict[str, str] = {
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
        print("\nLoaded Devices:")
        print_tabular_data(data, sort=sort)

        state = self.state(cached=False)
        if show_config_groups:
            group_data: defaultdict[str, list[str]] = defaultdict(list)
            groups = state["config_groups"]
            for group in groups:
                for pi, preset in enumerate(group["presets"]):
                    for si, stng in enumerate(preset["settings"]):
                        dev, prop, val = stng["dev"], stng["prop"], stng["val"]
                        group_name = group["name"] if (pi == 0 and si == 0) else ""
                        preset_name = preset["name"] if si == 0 else ""
                        group_data["Group"].append(group_name)
                        group_data["Preset"].append(preset_name)
                        group_data["Device"].append(dev)
                        group_data["Property"].append(prop)
                        group_data["Value"].append(val)
                    # add break between presets
                    group_data["Group"].append("")
                    group_data["Preset"].append("")
                    group_data["Device"].append("")
                    group_data["Property"].append("")
                    group_data["Value"].append("")

            print("\nConfig Groups:")
            print_tabular_data(group_data, sort=sort)

        if show_available:
            avail_data: defaultdict[str, list[str]] = defaultdict(list)
            avail_adapters = self.getDeviceAdapterNames()
            for adapt in avail_adapters:
                with suppress(Exception):
                    devices = self.getAvailableDevices(adapt)
                    descriptions = self.getAvailableDeviceDescriptions(adapt)
                    types = self.getAvailableDeviceTypes(adapt)
                    for dev, desc, type_ in zip(devices, descriptions, types):
                        avail_data["Library, DeviceName"].append(f"{adapt!r}, {dev!r}")
                        avail_data["Type"].append(str(DeviceType(type_)))
                        avail_data["Description"].append(desc)

            print("\nAvailable Devices:")
            print_tabular_data(avail_data, sort=sort)

    def state(
        self, *, cached: bool = True, include_time: bool = False, **_kwargs: Any
    ) -> SummaryMetaV1:
        """Return info on the current state of the core."""
        if _kwargs:
            keys = ", ".join(_kwargs.keys())
            warnings.warn(
                f"CMMCorePlus.state no longer takes arguments: {keys}. Ignoring."
                "Please update your code as this may be an error in the future.",
                stacklevel=2,
            )
        return summary_metadata(self, include_time=include_time, cached=cached)

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
        try:
            before = [self.getProperty(device, p) for p in properties]
        except Exception as e:
            logger.warning(
                "Error getting properties %s on %s: %s. "
                "Cannot ensure propertyChanged signal emission",
                properties,
                device,
                e,
            )
            yield
            return

        with _blockSignal(self.events, self.events.propertyChanged):
            yield
        after = [self.getProperty(device, p) for p in properties]
        if before != after:
            for i, val in enumerate(after):
                self.events.propertyChanged.emit(device, properties[i], val)

    @contextmanager
    def setContext(self, **kwargs: Unpack[SetContextKwargs]) -> Iterator[None]:
        """Set core properties in a context restoring the initial values on exit.

        :sparkles: *This method is new in `CMMCorePlus`.*

        Parameters
        ----------
        **kwargs : Any
            Keyword arguments may be any `Name` for which `get<Name>` and `set<Name>`
            methods exist (where the first letter in `<Name>` may be either lower or
            upper case).  For example, `setContext(exposure=10)` will call
            `setExposure(10)` when entering the context and `setExposure(<initial>)`
            when exiting the context. If the property is not found, a warning is logged
            and the property is skipped. If the value is a tuple, it is unpacked and
            passed to the `set<Name>` method (but lists are not unpacked).

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
                get_name, set_name = f"get{name}", f"set{name}"
                if not hasattr(self, get_name) or not hasattr(self, set_name):
                    logger.warning("%s is not a valid property, skipping.", name)
                    continue

                orig_values[name] = getattr(self, get_name)()
                if isinstance(v, tuple):
                    getattr(self, set_name)(*v)
                else:
                    getattr(self, set_name)(v)
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
        warnings.warn(
            "canSequenceEvents is deprecated.\nPlease use "
            "`list(pymmcore_plus.core.iter_sequenced_events(core, [e1, e2]))` "
            "to see how this core will combine MDAEvents into SequencedEvents.",
            DeprecationWarning,
            stacklevel=2,
        )
        from ._sequencing import can_sequence_events

        return can_sequence_events(self, e1, e2)


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
    def make_reemitter(name: str) -> Callable[..., None]:
        sig_name = name[2].lower() + name[3:]

        def reemit(self: _MMCallbackRelay, *args: Any) -> None:
            try:
                getattr(self._emitter, sig_name).emit(*args)
            except Exception as e:
                logger.error(
                    "Exception occurred in MMCorePlus callback %r: %s", sig_name, e
                )

        return reemit


MMCORE_SIGNAL_NAMES = {n for n in dir(pymmcore.MMEventCallback) if n.startswith("on")}
MMCallbackRelay = type(
    "MMCallbackRelay",
    (_MMCallbackRelay,),
    {n: _MMCallbackRelay.make_reemitter(n) for n in MMCORE_SIGNAL_NAMES},
)
