from __future__ import annotations

import atexit
import os
import re
import weakref
from contextlib import contextmanager, suppress
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from threading import RLock, Thread
from typing import (
    TYPE_CHECKING,
    Any,
    Iterator,
    Pattern,
    Sequence,
    TypeVar,
    Union,
    overload,
)

import pymmcore
from psygnal import SignalInstance
from typing_extensions import Literal
from wrapt import synchronized

from ._config import Configuration
from ._constants import DeviceDetectionStatus, DeviceType, PropertyType
from ._device import Device
from .._logger import logger
from ._metadata import Metadata
from ._property import DeviceProperty
from .._util import find_micromanager
from .events import CMMCoreSignaler, _get_auto_core_callback_class
from ..mda import MDAEngine, MDARunner, PMDAEngine

if TYPE_CHECKING:
    import numpy as np
    from useq import MDASequence

    _T = TypeVar("_T")
    ListOrTuple = Union[list[_T], tuple[_T, ...]]


_OBJECTIVE_DEVICE_RE = re.compile(
    "(.+)?(nosepiece|obj(ective)?)(turret)?s?", re.IGNORECASE
)
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
        Path to the Micro-Manager installation, by default None
    adapter_paths : Sequence[str], optional
        Paths to search for device adapters, by default ()
    """

    _lock = RLock()

    @classmethod
    def instance(
        cls, mm_path: str | None = None, adapter_paths: Sequence[str] = ()
    ) -> CMMCorePlus:
        global _instance
        if _instance is None:
            _instance = cls(mm_path, adapter_paths)
        return _instance

    def __init__(self, mm_path: str | None = None, adapter_paths: Sequence[str] = ()):
        super().__init__()

        self._mm_path = mm_path or find_micromanager()
        if not adapter_paths and self._mm_path:
            adapter_paths = [self._mm_path]
        if adapter_paths:
            self.setDeviceAdapterSearchPaths(adapter_paths)

        self.events = _get_auto_core_callback_class()()
        self._callback_relay = MMCallbackRelay(self.events)
        self.registerCallback(self._callback_relay)

        self._mda_runner = MDARunner()
        self._mda_runner.set_engine(MDAEngine(self))

        self._objective_regex = _OBJECTIVE_DEVICE_RE
        self._channel_group_regex = _CHANNEL_REGEX

        # use weakref to avoid atexit keeping us from being
        # garbage collected
        self._weak_clean = weakref.WeakMethod(self.unloadAllDevices)
        atexit.register(self._weak_clean)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} at {hex(id(self))}>"

    def __del__(self) -> None:
        atexit.unregister(self._weak_clean)
        self.unloadAllDevices()

    # Re-implemented methods from the CMMCore API

    @synchronized(_lock)
    def setProperty(
        self, label: str, propName: str, propValue: Union[bool, float, int, str]
    ) -> None:
        """setProperty with reliable event emission."""
        with self._property_change_emission_ensured(label, (propName,)):
            super().setProperty(label, propName, propValue)

    @synchronized(_lock)
    def setState(self, stateDeviceLabel: str, state: int) -> None:
        """Set state (by position) on stateDeviceLabel, with reliable event emission."""
        with self._property_change_emission_ensured(stateDeviceLabel, STATE_PROPS):
            super().setState(stateDeviceLabel, state)

    @synchronized(_lock)
    def setStateLabel(self, stateDeviceLabel: str, stateLabel: str) -> None:
        """Set state (by label) on stateDeviceLabel, with reliable event emission."""
        with self._property_change_emission_ensured(stateDeviceLabel, STATE_PROPS):
            super().setStateLabel(stateDeviceLabel, stateLabel)

    def setDeviceAdapterSearchPaths(self, paths: Sequence[str]) -> None:
        """Set the device adapter search paths."""
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

    @synchronized(_lock)
    def loadSystemConfiguration(
        self, fileName: str | Path = "MMConfig_demo.cfg"
    ) -> None:
        """Load a config file.

        For relative paths first checks relative to the current
        working directory, then in the device adapter path.
        """
        fpath = Path(fileName).expanduser()
        if not fpath.exists() and not fpath.is_absolute() and self._mm_path:
            fpath = Path(self._mm_path) / fileName
        if not fpath.exists():
            raise FileNotFoundError(f"Path does not exist: {fpath}")
        super().loadSystemConfiguration(str(fpath.resolve()))

    def unloadAllDevices(self) -> None:
        # this log won't appear when exiting ipython
        # but the method is still called
        logger.debug("Unloading all devices")
        return super().unloadAllDevices()

    def getDeviceType(self, label: str) -> DeviceType:
        """Returns device type."""
        return DeviceType(super().getDeviceType(label))

    def getPropertyType(self, label: str, propName: str) -> PropertyType:
        return PropertyType(super().getPropertyType(label, propName))

    def detectDevice(self, deviceLabel: str) -> DeviceDetectionStatus:
        """Tries to communicate to a device through a given serial port.

        Used to automate discovery of correct serial port.
        Also configures the serial port correctly.
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
        """Returns the configuration object for a given group and name."""
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
        """Returns the configuration object for a given pixel size preset."""
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
        """Returns the partial state of the system, for the devices included in the

        specified group.
        """
        cfg = super().getConfigGroupState(group)
        return cfg if native else Configuration.from_configuration(cfg)

    def getConfigGroupStateFromCache(
        self, group: str, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        """Returns the partial state of the system cache, for the devices included

        in the specified group.
        """
        cfg = super().getConfigGroupStateFromCache(group)
        return cfg if native else Configuration.from_configuration(cfg)

    def getConfigState(
        self, group: str, config: str, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        """Returns a partial state of the system, for devices included in the

        specified configuration.
        """
        cfg = super().getConfigState(group, config)
        return cfg if native else Configuration.from_configuration(cfg)

    def getSystemState(
        self, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        """Returns the entire system state."""
        cfg = super().getSystemState()
        return cfg if native else Configuration.from_configuration(cfg)

    def getSystemStateCache(
        self, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        """Returns the entire system state from cache"""
        cfg = super().getSystemStateCache()
        return cfg if native else Configuration.from_configuration(cfg)

    # metadata overloads that don't require instantiating metadata first

    @synchronized(_lock)
    def getLastImageMD(self, md: Metadata | None = None) -> tuple[np.ndarray, Metadata]:
        if md is None:
            md = Metadata()
        img = super().getLastImageMD(md)
        return img, md

    @synchronized(_lock)
    def popNextImageMD(self, md: Metadata | None = None) -> tuple[np.ndarray, Metadata]:
        if md is None:
            md = Metadata()
        img = super().popNextImageMD(md)
        return img, md

    @synchronized(_lock)
    def popNextImage(self) -> np.ndarray:
        """Gets and removes the next image from the circular buffer.

        The pymmcore-plus implementation will convert images with n_components > 1
        to a shape (w, h, num_components) and dtype `img.dtype.itemsize//ncomp`
        """
        return self._fix_image(super().popNextImage())

    @synchronized(_lock)
    def getNBeforeLastImageMD(
        self, n: int, md: Metadata | None = None
    ) -> tuple[np.ndarray, Metadata]:
        if md is None:
            md = Metadata()
        img = super().getNBeforeLastImageMD(n, md)
        return img, md

    def setConfig(self, groupName: str, configName: str) -> None:
        """Applies a configuration to a group."""
        super().setConfig(groupName, configName)
        # The onConfigGroupChanged callback has some limitations as
        # discussed in https://github.com/micro-manager/mmCoreAndDevices/issues/25
        # use the pymmcore-plus configSet signal as a workaround
        self.events.configSet.emit(groupName, configName)

    # NEW methods

    @overload
    def iterDevices(  # type: ignore
        self,
        device_type: DeviceType | None = ...,
        device_label: str | None = ...,
        as_object: Literal[False] = False,
    ) -> Iterator[str]:
        ...

    @overload
    def iterDevices(
        self,
        device_type: DeviceType | None = ...,
        device_label: str | None = ...,
        as_object: Literal[True] = ...,
    ) -> Iterator[Device]:
        ...

    def iterDevices(
        self,
        device_type: DeviceType | None = None,
        device_label: str | None = None,
        as_object: bool = False,
    ) -> Iterator[Device | str]:
        """Iterate over currently loaded devices.

        Parameters
        ----------
        device_type : DeviceType | None
            DeviceType to filter by, by default all device types will be yielded.
        device_label : str | None
            Device label to filter by, by default all device labels will be yielded.
        as_object : bool, optional
            If `True`, `Device` objects will be yielded instead of
            device label strings. By default False

        Yields
        ------
        Iterator[Union[Device, str]]
            `Device` objects (if `as_object==True`) or device label strings.
        """
        for dev in (
            self.getLoadedDevicesOfType(device_type)
            if device_type is not None
            else self.getLoadedDevices()
        ):
            if not device_label or dev == device_label:
                yield Device(dev, mmcore=self) if as_object else dev

    @overload
    def iterProperties(  # type: ignore
        self,
        device_type: DeviceType | None = ...,
        device_label: str | None = ...,
        property_type: PropertyType | None = ...,
        as_object: Literal[False] = False,
    ) -> Iterator[tuple[str, str]]:
        ...

    @overload
    def iterProperties(
        self,
        device_type: DeviceType | None = ...,
        device_label: str | None = ...,
        property_type: PropertyType | None = ...,
        as_object: Literal[True] = ...,
    ) -> Iterator[DeviceProperty]:
        ...

    def iterProperties(
        self,
        device_type: DeviceType | None = None,
        device_label: str | None = None,
        property_type: PropertyType | None = None,
        as_object: bool = False,
    ) -> Iterator[DeviceProperty | tuple[str, str]]:
        """Iterate over currently loaded (device_label, property_name) pairs.

        Parameters
        ----------
        device_type : DeviceType | None
            DeviceType to filter by, by default all device types will be yielded.
        device_label : str | None
            Device label to filter by, by default all device labels will be yielded.
        property_type : PropertyType | None
            PropertyType to filter by, by default all property types will be yielded.
        as_object : bool, optional
            If `True`, `DeviceProperty` objects will be yielded instead of
            `(device_label, property_name)` tuples. By default False

        Yields
        ------
        Iterator[Union[DeviceProperty, tuple[str, str]]]
            `DeviceProperty` objects (if `as_object==True`) or 2-tuples of (device_name,
            property_name)
        """
        for dev in self.iterDevices(device_type=device_type, device_label=device_label):
            for prop in self.getDevicePropertyNames(dev):
                if (
                    property_type is None
                    or self.getPropertyType(dev, prop) == property_type
                ):
                    yield DeviceProperty(dev, prop, self) if as_object else (dev, prop)

    def getPropertyObject(
        self, device_label: str, property_name: str
    ) -> DeviceProperty:
        """Return a DeviceProperty object bound to a device/property on this core."""
        return DeviceProperty(device_label, property_name, self)

    def getDeviceObject(self, device_label: str) -> Device:
        """Return a Device object bound to device_label on this core."""
        return Device(device_label, mmcore=self)

    def getDeviceSchema(self, device_label: str) -> dict[str, Any]:
        """Return dict in JSON-schema format for properties of `device_label`.

        Use `json.dump` to convert this dict to a JSON string.
        """
        # TODO: make TypeDict
        d: dict[str, Any] = {
            "title": self.getDeviceName(device_label),
            "description": self.getDeviceDescription(device_label),
            "type": "object",
            "properties": {},
        }
        for prop in self.iterProperties(device_label=device_label, as_object=True):
            p: dict[str, Any]
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
                p["sequence_max_length"] = prop.sequenceMaxLength()
            if prop.isPreInit():
                p["preInit"] = True
        if not d["properties"]:
            del d["properties"]
            del d["type"]
        return d

    @property
    def objective_device_pattern(self):
        return self._objective_regex

    @objective_device_pattern.setter
    def objective_device_pattern(self, value: Union[Pattern, str]):
        if isinstance(value, str):
            value = re.compile(value, re.IGNORECASE)
        elif not isinstance(value, Pattern):
            raise TypeError(
                "Objective Pattern must be a string or compiled regex"
                f" but is type {type(value)}"
            )
        self._objective_regex = value

    @property
    def channelGroup_pattern(self):
        return self._channelGroup_regex

    @channelGroup_pattern.setter
    def channelGroup_pattern(self, value: Union[Pattern, str]):
        if isinstance(value, str):
            value = re.compile(value, re.IGNORECASE)
        elif not isinstance(value, Pattern):
            raise TypeError(
                "channelGroup Pattern must be a string or compiled regex"
                f"but is type {type(value)}"
            )
        self._channel_group_regex = value

    def guessObjectiveDevices(self) -> list[str]:
        """
        Find any loaded devices that are likely to be an Objective/Nosepiece.

        Likely matches are loaded StateDevices with names that match this object's
        ``objective_device_pattern`` property. This is a settable property
        with a default value of::

            re.compile("(.+)?(nosepiece|obj(ective)?)(turret)?s?", re.IGNORECASE)``
        """
        return [
            device
            for device in self.getLoadedDevicesOfType(DeviceType.StateDevice)
            if self._objective_regex.match(device)
        ]

    def getOrGuessChannelGroup(self) -> list[str]:
        """Get the channelGroup or find a likely set of candidates.

        If the group is not defined via ``.getChannelGroup`` then likely candidates
        will be found by searching for config groups with names that match this
        object's ``channelGroup_pattern`` property. This is a settable property
        with a default value of::

            reg = re.compile("(chan{1,2}(el)?|filt(er)?)s?", re.IGNORECASE)

        """
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
        """Sets the relative XYZ position in microns."""
        if dx or dy:
            x, y = self.getXPosition(), self.getYPosition()
            self.setXYPosition(x + dx, y + dy)
        if dz:
            z = self.getPosition(self.getFocusDevice())
            self.setZPosition(z + dz)
        self.waitForDevice(self.getXYStageDevice())
        self.waitForDevice(self.getFocusDevice())

    def getZPosition(self) -> float:
        return self.getPosition(self.getFocusDevice())

    def setZPosition(self, val: float) -> None:
        return self.setPosition(self.getFocusDevice(), val)

    @overload
    def setPosition(self, position: float):
        ...

    @overload
    def setPosition(self, stageLabel: str, position: float):
        ...

    @synchronized(_lock)
    def setPosition(self, *args, **kwargs) -> None:
        """Set position of the stage in microns."""
        return super().setPosition(*args, **kwargs)

    @synchronized(_lock)
    def setXYPosition(self, x: float, y: float) -> None:
        return super().setXYPosition(x, y)

    @synchronized(_lock)
    def getCameraChannelNames(self) -> tuple[str, ...]:
        return tuple(
            self.getCameraChannelName(i)
            for i in range(self.getNumberOfCameraChannels())
        )

    @synchronized(_lock)
    def snapImage(self) -> None:
        return super().snapImage()

    @property
    def mda(self) -> MDARunner:
        return self._mda_runner

    def run_mda(self, sequence: MDASequence, block: bool = False) -> Thread:
        """Run MDA defined by *sequence* on a new thread.

        The currently registered MDAEngine (``core.mda``) will be responsible for
        executing the acquisition.

        After starting the sequence you can pause or cancel with the mda with
        the mda object's ``toggle_pause`` and ``cancel`` methods.

        Parameters
        ----------
        sequence : useq.MDASequence
            The useq.MDASequence to run.
        block : bool, optional
            If True, block until the sequence is complete, by default False.

        Returns
        -------
        Thread
            The thread the MDA is running on.  Use ``thread.join()`` to block until
            done, or ``thread.is_alive()`` to check if the sequence is complete.
        """
        if self.mda.is_running():
            raise ValueError(
                "Cannot start an MDA while the previous MDA is still running."
            )
        th = Thread(target=self.mda.run, args=(sequence,))
        th.start()
        if block:
            th.join()
        return th

    def register_mda_engine(self, engine: PMDAEngine) -> None:
        """Set the MDA Engine to be used on ``run_mda``.

        This will unregister the previous engine and emit an ``mdaEngineRegistered``
        signal. The current Engine must not be running an MDA in order to register a new
        engine.

        Parameters
        ----------
        engine : PMDAEngine
            Any object conforming to the PMDAEngine protocol.
        """
        old_engine = self.mda.set_engine(engine)
        self.events.mdaEngineRegistered.emit(engine, old_engine)

    def _fix_image(self, img: np.ndarray) -> np.ndarray:
        """Fix img shape/dtype based on `self.getNumberOfComponents()`.

        convert images with n_components > 1
        to a shape (w, h, num_components) and dtype `img.dtype.itemsize//ncomp`

        Parameters
        ----------
        img : np.ndarray
            input image

        Returns
        -------
        np.ndarray
            output image (possibly new shape and dtype)
        """
        if self.getNumberOfComponents() == 4:
            new_shape = img.shape + (4,)
            img = img.view(dtype=f"u{img.dtype.itemsize//4}")
            img = img.reshape(new_shape)[:, :, (2, 1, 0, 3)]  # mmcore gives bgra
        return img

    def snap(self, *args, fix=True) -> np.ndarray:
        """
        snap and return an image.

        In contrast to ``snapImage`` this will directly return the image
        without also calling ``getImage``.

        Parameters
        ----------
        *args :
            Passed through to ``getImage``
        fix : bool, default: True
            Whether to fix the shape of images with n_components >1
            Pass on to ``getImage``

        Returns
        -------
        img : np.ndarray
        """
        self.snapImage()
        img = self.getImage()
        self.events.imageSnapped.emit(img)
        return img

    def getImage(self, *args, fix=True) -> np.ndarray:
        """Exposes the internal image buffer.

        The pymmcore-plus implementation will convert images with n_components > 1
        to a shape (w, h, num_components) and dtype `img.dtype.itemsize//ncomp`
        """
        img = super().getImage(*args)
        return self._fix_image(img) if fix else img

    def startContinuousSequenceAcquisition(self, intervalMs: float = 0) -> None:
        """Start a ContinuousSequenceAcquisition."""
        super().startContinuousSequenceAcquisition(intervalMs)
        self.events.startContinuousSequenceAcquisition.emit()

    @overload
    def startSequenceAcquisition(
        self,
        numImages: int,
        intervalMs: float,
        stopOnOverflow: bool,
    ) -> None:
        ...  # pragma: no cover

    @overload
    def startSequenceAcquisition(
        self,
        cameraLabel: str,
        numImages: int,
        intervalMs: float,
        stopOnOverflow: bool,
    ) -> None:
        ...  # pragma: no cover

    def startSequenceAcquisition(self, *args, **kwargs) -> None:
        super().startSequenceAcquisition(*args, **kwargs)
        if len(args) == 3:
            numImages, intervalMs, stopOnOverflow = args
            cameraLabel = super().getCameraDevice()
        else:
            cameraLabel, numImages, intervalMs, stopOnOverflow = args
        self.events.startSequenceAcquisition.emit(
            cameraLabel, numImages, intervalMs, stopOnOverflow
        )

    def stopSequenceAcquisition(self, cameraLabel: str | None = None) -> None:
        """Stop a SequenceAcquisition."""
        if cameraLabel is None:
            super().stopSequenceAcquisition()
        else:
            super().stopSequenceAcquisition(cameraLabel)
        cameraLabel = cameraLabel or super().getCameraDevice()
        self.events.stopSequenceAcquisition.emit(cameraLabel)

    def setAutoShutter(self, state: bool):
        super().setAutoShutter(state)
        self.events.autoShutterSet.emit(state)

    @overload
    def setShutterOpen(self, state: bool) -> None:
        ...  # pragma: no cover

    @overload
    def setShutterOpen(self, shutterLabel: str, state: bool) -> None:
        ...  # pragma: no cover

    def setShutterOpen(self, *args):
        super().setShutterOpen(*args)
        if len(args) > 1:
            shutterLabel, state = args
        else:
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
        """Deletes a configuration from a group."""
        args: tuple[str, ...] = (groupName, configName)
        if deviceLabel is not None and propName is not None:
            args = args + (deviceLabel, propName)
        super().deleteConfig(*args)
        self.events.configDeleted.emit(groupName, configName)

    def deleteConfigGroup(self, group: str) -> None:
        super().deleteConfigGroup(group)
        self.events.configGroupDeleted.emit(group)

    @overload
    def defineConfig(self, groupName: str, configName: str) -> None:
        ...  # pragma: no cover

    @overload
    def defineConfig(
        self,
        groupName: str,
        configName: str,
        deviceLabel: str,
        propName: str,
        value: str,
    ) -> None:
        ...  # pragma: no cover

    def defineConfig(
        self,
        groupName: str,
        configName: str,
        deviceLabel: str | None = None,
        propName: str | None = None,
        value: str | None = None,
    ) -> None:
        """Defines a configuration."""
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
        super().setPixelSizeUm(resolutionID, pixSize)
        self.events.pixelSizeChanged.emit(pixSize)

    def deletePixelSizeConfig(self, resolutionID: str):
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
        super().definePixelSizeConfig(*args, **kwargs)
        self.events.pixelSizeChanged.emit(0.0)

    @overload
    def setROI(self, x: int, y: int, width: int, height: int) -> None:
        ...  # pragma: no cover

    @overload
    def setROI(self, label: str, x: int, y: int, width: int, height: int) -> None:
        ...  # pragma: no cover

    def setROI(self, *args) -> None:  # type: ignore
        super().setROI(*args)
        if len(args) == 4:
            args = (super().getCameraDevice(),) + args
        self.events.roiSet.emit(*args)

    def state(self, exclude=()) -> dict:
        """A dict with commonly accessed state values.  Faster than getSystemState."""
        # approx retrieval cost in comment (for demoCam)
        return {
            "AutoFocusDevice": self.getAutoFocusDevice(),  # 150 ns
            "BytesPerPixel": self.getBytesPerPixel(),  # 149 ns
            "CameraChannelNames": self.getCameraChannelNames(),  # 1 µs
            "CameraDevice": self.getCameraDevice(),  # 159 ns
            "Datetime": str(datetime.now()),
            "Exposure": self.getExposure(),  # 726 ns
            "FocusDevice": self.getFocusDevice(),  # 112 ns
            "GalvoDevice": self.getGalvoDevice(),  # 109 ns
            "ImageBitDepth": self.getImageBitDepth(),  # 147 ns
            "ImageHeight": self.getImageHeight(),  # 164 ns
            "ImageProcessorDevice": self.getImageProcessorDevice(),  # 110 ns
            "ImageWidth": self.getImageWidth(),  # 172 ns
            "PixelSizeUm": self.getPixelSizeUm(True),  # 2.2 µs  (True==cached)
            "ShutterDevice": self.getShutterDevice(),  # 152 ns
            "SLMDevice": self.getSLMDevice(),  # 110 ns
            "XYPosition": self.getXYPosition(),  # type: ignore  # 1.1 µs
            "XYStageDevice": self.getXYStageDevice(),  # 156 ns
            "ZPosition": self.getZPosition(),  # 1.03 µs
        }

    @contextmanager
    def _property_change_emission_ensured(self, device: str, properties: Sequence[str]):
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
    def setContext(self, **kwargs):
        """Set core properties in a context restoring the initial values on exit."""
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
    def _make_reemitter(name):
        sig_name = name[2].lower() + name[3:]

        def reemit(self: _MMCallbackRelay, *args):
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
