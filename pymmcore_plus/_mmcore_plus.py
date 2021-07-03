from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

import pymmcore
from loguru import logger

if TYPE_CHECKING:
    import useq

    from ._client import CallbackProtocol


class CMMCorePlus(pymmcore.CMMCore):
    def __init__(self, mm_path=None, adapter_paths: Sequence[str] = ()):
        super().__init__()

        if not mm_path:
            from ._util import find_micromanager

            mm_path = find_micromanager()

        self._mm_path = mm_path
        if not adapter_paths and mm_path:
            adapter_paths = [mm_path]
        if adapter_paths:
            self.setDeviceAdapterSearchPaths(adapter_paths)
        self._callback_relay = MMCallbackRelay(self)
        self.registerCallback(self._callback_relay)
        self._canceled = False
        self._paused = False
        self._callback_handlers: set[CallbackProtocol] = set()

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

    def run_mda(self, sequence: useq.MDASequence) -> None:
        self.emit_signal("onMDAStarted", sequence)
        self._paused = False
        logger.info("MDA Started: {}", sequence)
        t0 = time.perf_counter()  # reference time, in seconds
        paused_time = 0.0
        for event in sequence:
            while self._paused and not self._canceled:
                paused_time += 0.1  # fixme: be more precise
                time.sleep(0.1)
            if self._canceled:
                logger.warning("MDA Canceled: {}", sequence)
                self.emit_signal("onMDACanceled")
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

            self.emit_signal("onMDAFrameReady", img, event)
        logger.info("MDA Finished: {}", sequence)
        self.emit_signal("onMDAFinished", sequence)

    def cancel(self):
        self._canceled = True

    def toggle_pause(self):
        self._paused = not self._paused
        self.emit_signal("onMDAPauseToggled", self._paused)

    def connect_remote_callback(self, handler: CallbackProtocol):
        self._callback_handlers.add(handler)

    def disconnect_remote_callback(self, handler: CallbackProtocol):
        self._callback_handlers.discard(handler)

    def emit_signal(self, signal_name: str, *args):
        # different in pyro subclass
        logger.debug("{}: {}", signal_name, args)
        for handler in self._callback_handlers:
            handler.receive_core_callback(signal_name, args)


class MMCallbackRelay(pymmcore.MMEventCallback):
    def __init__(self, core: CMMCorePlus):
        super().__init__()
        self._core = core

    def onPropertiesChanged(self):
        self._core.emit_signal("onPropertiesChanged")

    def onPropertyChanged(self, dev_name: str, prop_name: str, prop_val: str):
        self._core.emit_signal("onPropertyChanged", dev_name, prop_name, prop_val)

    def onChannelGroupChanged(self, new_channel_group_name: str):
        self._core.emit_signal("onChannelGroupChanged", new_channel_group_name)

    def onConfigGroupChanged(self, group_name: str, new_config_name: str):
        self._core.emit_signal("onConfigGroupChanged", group_name, new_config_name)

    def onSystemConfigurationLoaded(self):
        self._core.emit_signal("onSystemConfigurationLoaded")

    def onPixelSizeChanged(self, new_pixel_size_um: float):
        self._core.emit_signal("onPixelSizeChanged", new_pixel_size_um)

    def onPixelSizeAffineChanged(self, v0, v1, v2, v3, v4, v5):
        self._core.emit_signal("onPixelSizeAffineChanged", v0, v1, v2, v3, v4, v5)

    def onStagePositionChanged(self, name: str, pos: float):
        self._core.emit_signal("onStagePositionChanged", name, pos)

    def onXYStagePositionChanged(self, name: str, xpos: float, ypos: float):
        self._core.emit_signal("onXYStagePositionChanged", name, xpos, ypos)

    def onExposureChanged(self, name: str, new_exposure: float):
        self._core.emit_signal("onExposureChanged", name, new_exposure)

    def onSLMExposureChanged(self, name: str, new_exposure: float):
        self._core.emit_signal("onSLMExposureChanged", name, new_exposure)
