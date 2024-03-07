"""Questions for nathan.

- Is there a runtime singleton?
    acquire.Runtime() is acquire.Runtime()  # False
    Is the user expected to manage the lifetime of the runtime?
    What happens if the runtime is garbage collected?
    How do devices handle being managed by multiple runtimes?

- Is there a device_manager singleton?
    runtime.device_manager() is runtime.device_manager()  # False
    are identifiers tied to a specific device_manager, or to the runtime?

- where does one look to find all the valid strings for dm.select?
- CameraProperties.offset is confusing, could be conflated with camera amplifier offset
  rather than the ROI offset.
- enums like SampleType should be proper enums; or at least have a __members__
  attribute for introspection, a __getitem__ method for reverse lookup, and
  a __call__ method for conversion.
- RuntimeError: Failed acquire api status check
    could be more informative?
- somewhat confusing that you set the shape as (width, height) but receive data
  as (height, width)
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, Literal

import acquire
from rich import print

if TYPE_CHECKING:
    import numpy.typing as npt

RT: acquire.Runtime | None = None
DM: acquire.acquire.DeviceManager | None = None


def get_runtime() -> acquire.Runtime:
    global RT
    if RT is None:
        logging.getLogger("acquire").setLevel(logging.CRITICAL)
        RT = acquire.Runtime()
        logging.getLogger("acquire").setLevel(logging.WARNING)
    return RT


class AcquireCamera:
    def __init__(
        self, stream_id: Literal[0, 1] = 0, source: str = "simulated: radial sin"
    ):
        self._stream_id = stream_id
        self.rt = get_runtime()
        self.source = source

    @property
    def source(self) -> str:
        """Return the source of the camera."""
        return self._source

    @source.setter
    def source(self, source: str) -> None:
        cfg = self.rt.get_configuration()
        dm = self.rt.device_manager()

        stream = cfg.video[self._stream_id]
        stream.camera.identifier = dm.select(acquire.DeviceKind.Camera, source)
        stream.storage.identifier = dm.select(acquire.DeviceKind.Storage, "Trash")

        self.rt.set_configuration(cfg)
        self._source = source

    @property
    def exposure_time(self) -> float:
        """Return the exposure time of the camera in microseconds."""
        return self.properties.exposure_time_us

    @property
    def properties(self) -> acquire.acquire.CameraProperties:
        """Return the properties of the camera."""
        return self.rt.get_configuration().video[self._stream_id].camera.settings

    def set_exposure_time_ms(self, exposure_time_ms: float) -> None:
        """Set the exposure time of the camera in milliseconds."""
        self._set_property("exposure_time_us", exposure_time_ms * 1e3)

    def set_shape(self, shape: tuple[int, int]) -> None:
        """Set the shape (ROI) of the camera."""
        self._set_property("shape", shape)

    def set_pixel_type(self, pixel_type: acquire.acquire.SampleType) -> None:
        """Set the pixel type of the camera."""
        self._set_property("pixel_type", pixel_type)

    def _set_property(self, name: str, value: Any) -> None:
        cfg = self.rt.get_configuration()
        setattr(cfg.video[self._stream_id].camera.settings, name, value)
        self.rt.set_configuration(cfg)

    def snap_image(self) -> Future[npt.NDArray]:
        """Snap an image and return a future with the image data."""
        cfg = self.rt.get_configuration()
        cfg.video[self._stream_id].max_frame_count = 2
        self.rt.set_configuration(cfg)
        self.rt.start()

        result: Future[npt.NDArray] = Future()

        while self.rt.get_state() == acquire.acquire.DeviceState.Running:
            time.sleep(0.01)

        with self.rt.get_available_data(self._stream_id) as data:
            frame = next(data.frames())
            result.set_result(frame.data().squeeze())

        return result


cam = AcquireCamera()
cam.set_exposure_time_ms(5)
cam.set_shape((256, 356))
# cam.set_pixel_type(acquire.acquire.SampleType.U12)
print(cam.properties)
fut = cam.snap_image()
print(fut.result().shape)
