from __future__ import annotations

import logging
import time
from concurrent.futures import Future
from typing import TYPE_CHECKING, Literal, TypedDict, cast

import acquire
from rich import print

if TYPE_CHECKING:
    import acquire.acquire as acq
    import numpy.typing as npt
    from typing_extensions import Unpack

    class CameraPropertiesDict(TypedDict, total=False):
        """Settings for the camera."""

        exposure_time_us: float
        line_interval_us: float
        binning: float
        pixel_type: acq.SampleType
        readout_direction: acq.Direction
        offset: tuple[int, int]
        shape: tuple[int, int]
        input_triggers: acq.InputTriggers
        output_triggers: acq.OutputTriggers


RT: acquire.Runtime | None = None
DM: acquire.acquire.DeviceManager | None = None


def get_runtime() -> acquire.Runtime:
    """Return the runtime singleton."""
    global RT
    if RT is None:
        logging.getLogger("acquire").setLevel(logging.CRITICAL)
        RT = acquire.Runtime()
        logging.getLogger("acquire").setLevel(logging.WARNING)
    return RT


class AcquireCamera:
    """A wrapper around a camera device in the acquire-python library."""

    def __init__(
        self,
        stream_id: Literal[0, 1] = 0,
        device_name: str | None = "simulated: radial sin",
        storage_name: str | None = None,
    ):
        self._stream_id = stream_id
        self.rt = get_runtime()
        self._storage_name: str = ""
        self._device_name: str = ""

        self.set_storage(storage_name)
        self.set_device_name(device_name)

    @property
    def device_name(self) -> str:
        """Return the source of the camera."""
        return self._device_name

    @property
    def properties(self) -> acquire.acquire.CameraProperties:
        """Return the properties of the camera."""
        return self.rt.get_configuration().video[self._stream_id].camera.settings

    def set_device_name(self, name: str | None) -> None:
        """Set a camera device from the device manager by name."""
        dm = self.rt.device_manager()

        if not (ident := dm.select(acquire.DeviceKind.Camera, name)):
            options = {
                d.name for d in dm.devices() if d.kind == acquire.DeviceKind.Camera
            }
            raise ValueError(f"Camera device {name!r} not found. Options: {options}.")

        cfg = self.rt.get_configuration()
        cfg.video[self._stream_id].camera.identifier = ident

        self.rt.set_configuration(cfg)
        self._device_name = ident.name

    def set_storage(self, name: str | None) -> None:
        """Set the storage device for this camera."""
        dm = self.rt.device_manager()

        # override with trash if None
        # acquire's default behavior is to use the first one available, which is "raw"
        # i think it makes more sense to use "trash" for "storage = None"
        name = name or "trash"
        if not (ident := dm.select(acquire.DeviceKind.Storage, name)):
            options = {
                d.name for d in dm.devices() if d.kind == acquire.DeviceKind.Storage
            }
            raise ValueError(f"Camera device {name!r} not found. Options: {options}.")

        cfg = self.rt.get_configuration()
        cfg.video[self._stream_id].storage.identifier = ident
        self.rt.set_configuration(cfg)

        self._storage_name = ident.name

    def set_exposure_time_ms(self, exposure_time_ms: float) -> None:
        """Set the exposure time of the camera in milliseconds."""
        self.update_settings(exposure_time_us=exposure_time_ms * 1e3)

    def update_settings(self, **settings: Unpack[CameraPropertiesDict]) -> None:
        """Update the settings of the camera.

        Keywords may be any field from acquire.CameraProperties
        """
        cfg = self.rt.get_configuration()
        for key, value in settings.items():
            setattr(cfg.video[self._stream_id].camera.settings, key, value)
        self.rt.set_configuration(cfg)

    def snap_image_blocking(self) -> npt.NDArray:
        """Snap a single image and return the image data, blocks the thread."""
        # this seems a bit ugly
        # i'm not sure acquire is designed to be used to "snap" a single image
        cfg = self.rt.get_configuration()
        if cfg.video[self._stream_id].max_frame_count != 1:
            cfg.video[self._stream_id].max_frame_count = 1
            self.rt.set_configuration(cfg)

        self.rt.start()
        while self.rt.get_state() == acquire.acquire.DeviceState.Running:
            # is there a better way?
            time.sleep(0.01)

        with self.rt.get_available_data(self._stream_id) as data:
            if (frame := next(data.frames(), None)) is not None:
                return cast("npt.NDArray", frame.data().squeeze())
        raise RuntimeError("No frame available.")

    def snap_image(self) -> Future[npt.NDArray]:
        """Snap a single image and return a Future with the image data."""
        result: Future[npt.NDArray] = Future()
        # NOTE: ask Nathan about threading here
        result.set_result(self.snap_image_blocking())
        return result

    def prepare_sequence(self, nframes: int) -> None:
        """Prepare for a sequence of nframes."""

    def start_sequence(self) -> None:
        """Start the sequence of frames."""


if __name__ == "__main__":
    cam = AcquireCamera()
    cam.update_settings(exposure_time_us=50e3, shape=(256, 256))
    print(cam.properties)
    fut = cam.snap_image()
    result = fut.result()
    print(result.shape, result.mean())
