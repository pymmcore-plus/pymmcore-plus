from __future__ import annotations

import atexit
import os
import time
import weakref
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, TypeVar, Union

import pymmcore
from loguru import logger

from .._util import find_micromanager
from ._config import Configuration
from ._constants import DeviceDetectionStatus, DeviceType, PropertyType
from ._metadata import Metadata
from ._signals import _CMMCoreSignaler

if TYPE_CHECKING:
    import numpy as np
    from useq import MDASequence

_T = TypeVar("_T")

ListOrTuple = Union[List[_T], Tuple[_T, ...]]


class CMMCorePlus(pymmcore.CMMCore):
    def __init__(self, mm_path=None, adapter_paths: ListOrTuple[str] = ()):
        super().__init__()

        self._mm_path = mm_path or find_micromanager()
        if not adapter_paths and self._mm_path:
            adapter_paths = [self._mm_path]
        if adapter_paths:
            self.setDeviceAdapterSearchPaths(adapter_paths)

        self.events = _CMMCoreSignaler()
        self._callback_relay = MMCallbackRelay(self.events)
        self.registerCallback(self._callback_relay)
        self._canceled = False
        self._paused = False

        # use weakref to avoid atexit keeping us from being
        # garbage collected
        self._weak_clean = weakref.WeakMethod(self.unloadAllDevices)
        atexit.register(self._weak_clean)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} at {hex(id(self))}>"

    def __del__(self):
        atexit.unregister(self._weak_clean)
        self.unloadAllDevices()

    # Re-implemented methods from the CMMCore API

    def setProperty(
        self, label: str, propName: str, propValue: Union[bool, float, int, str]
    ) -> None:
        """setProperty with more reliable event emission.

        As stated by Nico: "Callbacks are mainly used to give devices the opportunity to
        signal back to the UI."
        https://forum.image.sc/t/micromanager-events-core-events-not-coming-through/53014/2

        Because it's left to the device adapter to emit a signal, in many cases uses
        `setProperty()` will NOT lead to a new `propertyChanged` event getting emitted.
        But that makes it hard to create listeners (i.e. in the gui or elsewhere).

        While this method override cannot completely solve that problem (core-internal
        changes will still lack an associated event emission in many cases), it can at
        least guarantee that if we use `CMMCorePlus.setProperty` to change the property,
        then a `propertyChanged` event will be emitted if the value did indeed change.

        Parameters
        ----------
        label : str
            device label
        propName : str
            property name
        propValue : Union[bool, float, int, str]
            new value
        """
        before = super().getProperty(label, propName)
        with self.events.propertyChanged.blocked():  # block the native event.
            super().setProperty(label, propName, propValue)
        after = super().getProperty(label, propName)
        if before != after:
            self.events.propertyChanged.emit(label, propName, after)

    def setDeviceAdapterSearchPaths(self, adapter_paths: ListOrTuple[str]) -> None:
        # add to PATH as well for dynamic dlls
        if (
            not isinstance(adapter_paths, (list, tuple))
            and adapter_paths
            and all(isinstance(i, str) for i in adapter_paths)
        ):
            raise TypeError("adapter paths must be a sequence of strings")
        env_path = os.environ["PATH"]
        for p in adapter_paths:
            if p not in env_path:
                env_path = p + os.pathsep + env_path
        os.environ["PATH"] = env_path
        logger.info(f"setting adapter search paths: {adapter_paths}")
        super().setDeviceAdapterSearchPaths(adapter_paths)

    def loadSystemConfiguration(self, fileName="demo") -> None:
        if fileName.lower() == "demo":
            if not self._mm_path:
                raise ValueError(  # pragma: no cover
                    "No micro-manager path provided. Cannot load 'demo' file.\nTry "
                    "installing micro-manager with `python install_mm.py`"
                )
            fileName = (Path(self._mm_path) / "MMConfig_demo.cfg").resolve()
        super().loadSystemConfiguration(str(fileName))

    def unloadAllDevices(self) -> None:
        # this log won't appear when exiting ipython
        # but the method is still called
        logger.info("Unloading all devices")
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

    def getConfigData(
        self, configGroup: str, configName: str, *, native=False
    ) -> Configuration:
        """Returns the configuration object for a given group and name."""

        cfg = super().getConfigData(configGroup, configName)
        return cfg if native else Configuration.from_configuration(cfg)

    def getConfigGroupState(self, group: str, *, native=False) -> Configuration:
        """Returns the partial state of the system, for the devices included in the
        specified group.
        """
        cfg = super().getConfigGroupState(group)
        return cfg if native else Configuration.from_configuration(cfg)

    def getConfigGroupStateFromCache(
        self, group: str, *, native=False
    ) -> Configuration:
        """Returns the partial state of the system cache, for the devices included
        in the specified group.
        """
        cfg = super().getConfigGroupStateFromCache(group)
        return cfg if native else Configuration.from_configuration(cfg)

    def getConfigState(self, group: str, config: str, *, native=False) -> Configuration:
        """Returns a partial state of the system, for devices included in the
        specified configuration.
        """
        cfg = super().getConfigState(group, config)
        return cfg if native else Configuration.from_configuration(cfg)

    def getSystemState(self, *, native=False) -> Configuration:
        """Returns the entire system state."""
        cfg = super().getSystemState()
        return cfg if native else Configuration.from_configuration(cfg)

    def getSystemStateCache(self, *, native=False) -> Configuration:
        """Returns the entire system state from cache"""
        cfg = super().getSystemStateCache()
        return cfg if native else Configuration.from_configuration(cfg)

    # metadata overloads that don't require instantiating metadata first

    def getLastImageMD(
        self, md: Optional[Metadata] = None
    ) -> Tuple[np.ndarray, Metadata]:
        if md is None:
            md = Metadata()
        img = super().getLastImageMD(md)
        return img, md

    def popNextImageMD(
        self, md: Optional[Metadata] = None
    ) -> Tuple[np.ndarray, Metadata]:
        if md is None:
            md = Metadata()
        img = super().popNextImageMD(md)
        return img, md

    def popNextImage(self) -> np.ndarray:
        """Gets and removes the next image from the circular buffer.

        The pymmcore-plus implementation will convert images with n_components > 1
        to a shape (w, h, num_components) and dtype `img.dtype.itemsize//ncomp`
        """
        return self._fix_image(super().popNextImage())

    def getNBeforeLastImageMD(
        self, n: int, md: Optional[Metadata] = None
    ) -> Tuple[np.ndarray, Metadata]:
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

    def getDeviceProperties(self, device_label: str) -> Dict[str, Any]:
        """Return all current properties for device `device_label`."""
        return {
            name: self.getProperty(device_label, name)
            for name in self.getDevicePropertyNames(device_label)
        }

    def getDeviceSchema(self, device_label: str) -> Dict[str, Any]:
        """Return dict in JSON-schema format for propties of `device_label`.

        Use `json.dump` to convert this dict to a JSON string.
        """
        d = {
            "title": self.getDeviceName(device_label),
            "description": self.getDeviceDescription(device_label),
            "type": "object",
            "properties": {},
        }
        for prop_name in self.getDevicePropertyNames(device_label):
            _type = self.getPropertyType(device_label, prop_name)
            d["properties"][prop_name] = p = {}
            if _type.to_json() != "null":
                p["type"] = _type.to_json()
            if self.hasPropertyLimits(device_label, prop_name):
                min_ = self.getPropertyLowerLimit(device_label, prop_name)
                max_ = self.getPropertyUpperLimit(device_label, prop_name)
                p["minimum"] = min_
                p["maximum"] = max_
            allowed = self.getAllowedPropertyValues(device_label, prop_name)
            if allowed:
                if set(allowed) == {"0", "1"} and _type.to_json() == "integer":
                    p["type"] = "boolean"
                else:
                    cls = _type.to_python()
                    p["enum"] = [cls(i) if cls else i for i in allowed]
            if self.isPropertyReadOnly(device_label, prop_name):
                p["readOnly"] = True
                p["default"] = self.getProperty(device_label, prop_name)
            if self.isPropertySequenceable(device_label, prop_name):
                p["sequenceable"] = True
                p["sequence_max_length"] = self.getPropertySequenceMaxLength(
                    device_label, prop_name
                )
            if self.isPropertyPreInit(device_label, prop_name):
                p["preInit"] = True
        if not d["properties"]:
            del d["properties"]
            del d["type"]
        return d

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

    def getCameraChannelNames(self) -> Tuple[str, ...]:
        return tuple(
            self.getCameraChannelName(i)
            for i in range(self.getNumberOfCameraChannels())
        )

    def run_mda(self, sequence: MDASequence) -> None:
        self.events.sequenceStarted.emit(sequence)
        logger.info("MDA Started: {}", sequence)
        self._paused = False
        paused_time = 0.0
        t0 = time.perf_counter()  # reference time, in seconds

        def check_canceled():
            if self._canceled:
                logger.warning("MDA Canceled: {}", sequence)
                self.events.sequenceCanceled.emit(sequence)
                self._canceled = False
                return True
            return False

        for event in sequence:
            while self._paused and not self._canceled:
                paused_time += 0.1  # fixme: be more precise
                time.sleep(0.1)

            if check_canceled():
                break

            if event.min_start_time:
                go_at = event.min_start_time + paused_time
                # We need to enter a loop here checking paused and canceled.
                # otherwise you'll potentially wait a long time to cancel
                to_go = go_at - (time.perf_counter() - t0)
                while to_go > 0:
                    while self._paused and not self._canceled:
                        paused_time += 0.1  # fixme: be more precise
                        to_go += 0.1
                        time.sleep(0.1)

                    if self._canceled:
                        break
                    if to_go > 0.5:
                        time.sleep(0.5)
                    else:
                        time.sleep(to_go)
                    to_go = go_at - (time.perf_counter() - t0)

            # check canceled again in case it was canceled
            # during the waiting loop
            if check_canceled():
                break

            logger.info(event)

            # prep hardware
            if event.x_pos is not None or event.y_pos is not None:
                x = event.x_pos or self.getXPosition()
                y = event.y_pos or self.getYPosition()
                self.setXYPosition(x, y)
            if event.z_pos is not None:
                self.setZPosition(event.z_pos)
            if event.channel is not None:
                self.setConfig(event.channel.group, event.channel.config)
            if event.exposure is not None:
                self.setExposure(event.exposure)

            # acquire
            self.waitForSystem()
            self.snapImage()
            img = self.getImage()

            self.events.frameReady.emit(img, event)

        logger.info("MDA Finished: {}", sequence)
        self.events.sequenceFinished.emit(sequence)

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

    def getImage(self, *args, fix=True) -> np.ndarray:
        """Exposes the internal image buffer.

        The pymmcore-plus implementation will convert images with n_components > 1
        to a shape (w, h, num_components) and dtype `img.dtype.itemsize//ncomp`
        """
        img = super().getImage(*args)
        return self._fix_image(img) if fix else img

    def cancel(self):
        self._canceled = True

    def toggle_pause(self):
        self._paused = not self._paused
        self.events.sequencePauseToggled.emit(self._paused)

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
            "XYPosition": self.getXYPosition(),  # 1.1 µs
            "XYStageDevice": self.getXYStageDevice(),  # 156 ns
            "ZPosition": self.getZPosition(),  # 1.03 µs
        }


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

    def __init__(self, emitter: _CMMCoreSignaler):
        self._emitter = emitter
        super().__init__()

    @staticmethod
    def _make_reemitter(name):
        sig_name = name[2].lower() + name[3:]

        def reemit(self: _MMCallbackRelay, *args):
            try:
                getattr(self._emitter, sig_name).emit(*args)
            except Exception as e:
                import logging

                logging.getLogger(__name__).error(
                    "Exception occured in MMCorePlus callback %s: %s"
                    % (repr(sig_name), str(e))
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
