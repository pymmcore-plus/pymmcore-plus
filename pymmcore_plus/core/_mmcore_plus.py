from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence, Tuple

import pymmcore
from loguru import logger
from pymmcore import CMMCore

from .._util import find_micromanager
from ._constants import DeviceDetectionStatus, DeviceType, PropertyType
from ._metadata import Metadata
from ._signals import _CMMCoreSignaler

if TYPE_CHECKING:
    import numpy as np
    from useq import MDASequence


class CMMCorePlus(CMMCore, _CMMCoreSignaler):
    def __init__(self, mm_path=None, adapter_paths: Sequence[str] = ()):
        super().__init__()

        self._mm_path = mm_path or find_micromanager()
        if not adapter_paths and self._mm_path:
            adapter_paths = [self._mm_path]
        if adapter_paths:
            self.setDeviceAdapterSearchPaths(adapter_paths)

        self._callback_relay = MMCallbackRelay(self)
        self.registerCallback(self._callback_relay)
        self._canceled = False
        self._paused = False

    # Re-implemented methods from the CMMCore API

    def setDeviceAdapterSearchPaths(self, adapter_paths: Sequence[str]):
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

    def loadSystemConfiguration(self, fileName="demo"):
        if fileName.lower() == "demo":
            if not self._mm_path:
                raise ValueError(
                    "No micro-manager path provided. Cannot load 'demo' file.\nTry "
                    "installing micro-manager with `python install_mm.py`"
                )
            fileName = (Path(self._mm_path) / "MMConfig_demo.cfg").resolve()
        super().loadSystemConfiguration(str(fileName))

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

    def getNBeforeLastImageMD(
        self, n: int, md: Optional[Metadata] = None
    ) -> Tuple[np.ndarray, Metadata]:
        if md is None:
            md = Metadata()
        img = super().getNBeforeLastImageMD(n, md)
        return img, md

    # NEW methods

    def setRelPosition(self, dx: float = 0, dy: float = 0, dz: float = 0) -> None:
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
        self.sequenceStarted.emit(sequence)
        logger.info("MDA Started: {}", sequence)
        self._paused = False
        paused_time = 0.0
        t0 = time.perf_counter()  # reference time, in seconds
        for event in sequence:
            while self._paused and not self._canceled:
                paused_time += 0.1  # fixme: be more precise
                time.sleep(0.1)
            if self._canceled:
                logger.warning("MDA Canceled: {}", sequence)
                self.sequenceCanceled.emit(sequence)
                self._canceled = False
                break

            if event.min_start_time:
                go_at = event.min_start_time + paused_time
                # TODO: we need to enter a loop here checking paused and canceled.
                # otherwise you'll potentially wait a long time to cancel
                if go_at > time.perf_counter() - t0:
                    time.sleep(go_at - (time.perf_counter() - t0))
            logger.info(event)

            # prep hardware
            if event.x_pos is not None or event.y_pos is not None:
                x = event.x_pos or self.getXPosition()
                y = event.y_pos or self.getYPosition()
                self.setXYPosition(x, y)
            if event.z_pos is not None:
                self.setZPosition(event.z_pos)
            if event.exposure is not None:
                self.setExposure(event.exposure)
            if event.channel is not None:
                self.setConfig(event.channel.group, event.channel.config)

            # acquire
            self.waitForSystem()
            self.snapImage()
            img = self.getImage()

            self.frameReady.emit(img, event)

        logger.info("MDA Finished: {}", sequence)
        self.sequenceFinished.emit(sequence)

    def cancel(self):
        self._canceled = True

    def toggle_pause(self):
        self._paused = not self._paused
        self.sequencePauseToggled.emit(self._paused)

    def state(self) -> dict:
        # approx retrieval cost in comment (for demoCam)
        return {
            "bytest_per_pixel": self.getBytesPerPixel(),  # 149 ns
            "image_bit_depth": self.getImageBitDepth(),  # 147 ns
            "image_width": self.getImageWidth(),  # 172 ns
            "image_height": self.getImageHeight(),  # 164 ns
            "pixel_size_um": self.getPixelSizeUm(),  # 2.83 µs
            "xy_stage_device": self.getXYStageDevice(),  # 156 ns
            "xy_position": self.getXYPosition(),  # 1.1 µs
            "focus_device": self.getFocusDevice(),  # 112 ns
            "focus_position": self.getZPosition(),  # 1.03 µs
            "auto_focus_device": self.getAutoFocusDevice(),  # 150 ns
            "camera_device": self.getCameraDevice(),  # 159 ns
            "exposure": self.getExposure(),  # 726 ns
            "camera_channels": self.getCameraChannelNames(),  # 1 µs
            "galvo_device": self.getGalvoDevice(),  # 109 ns
            "image_processor_device": self.getImageProcessorDevice(),  # 110 ns
            "slm_device": self.getSLMDevice(),  # 110 ns
            "shutter_device": self.getShutterDevice(),  # 152 ns
            "datetime": str(datetime.now()),
        }


class _MMCallbackRelay:
    """Relays MMEventCallback methods to CMMCorePlus.signal."""

    def __init__(self, core: CMMCorePlus):
        self._core = core
        super().__init__()

    @staticmethod
    def _make_reemitter(name):
        sig_name = name[2].lower() + name[3:]

        def reemit(self: _MMCallbackRelay, *args):
            getattr(self._core, sig_name).emit(*args)

        return reemit


MMCallbackRelay = type(
    "MMCallbackRelay",
    (_MMCallbackRelay, pymmcore.MMEventCallback),
    {
        n: _MMCallbackRelay._make_reemitter(n)
        for n in dir(pymmcore.MMEventCallback)
        if n.startswith("on")
    },
)
