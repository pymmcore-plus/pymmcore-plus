"""Example of using combined C and Python devices in UniCore.

Unicore is a subclass of MMCore that allows for loading Python devices, which must be
subclasses of `pymmcore_plus.unicore.Device`. The final API is unchanged from
CMMCorePlus: the Unicore knows whether a device label corresponds to a C++ or Python
device and routes the call accordingly.

This example demonstrates how to create a custom Python camera device that uses the
Hamamatsu DCAM API to acquire images from a Hamamatsu camera.
"""

try:
    import pyDCAM as dc
except Exception as e:
    raise ImportError(
        "This example requires:\n\n"
        "    1. Windows OS\n"
        "    2. Hamamatsu DCAM API installed\n"
        "       https://www.hamamatsu.com/jp/en/product/cameras/software/driver-software/dcam-api-for-windows.html\n"
        "    3. pyDCAM to be installed: `pip install pyDCAM`\n\n"
    ) from e

import ctypes as c
import time
from collections.abc import Iterator, Mapping, Sequence
from typing import Callable

import numpy as np
from numpy.typing import DTypeLike

from pymmcore_plus.experimental.unicore import Camera, UniMMCore

dll = dc.dcamapi


PIXEL_TYPE_TO_DTYPE: dict[int, np.dtype] = {
    dc.DCAM_PIXELTYPE.DCAM_PIXELTYPE_MONO8: np.dtype(np.uint8),
    dc.DCAM_PIXELTYPE.DCAM_PIXELTYPE_MONO16: np.dtype(np.uint16),
}

# -------- Here is our actual Device Adaptor for pymmcore_plus.unicore.Camera


class HamaCam(Camera):
    def initialize(self) -> None:
        """Initialize the camera."""
        if count := dc.dcamapi_init():
            print(f"DCAM API initialized. Found {count} devices.")
        else:
            raise RuntimeError("Failed to initialize DCAM API")

        self._hdcam = dc.HDCAM()

    def shutdown(self) -> None:
        self._hdcam.dcamdev_close()
        dc.dcamapi_uninit()

    def get_exposure(self) -> float:
        exp = self._hdcam.dcamprop_getvalue(dc.DCAMIDPROP.DCAM_IDPROP_EXPOSURETIME)
        return exp * 1000.0

    def set_exposure(self, exposure: float) -> None:
        """Set the exposure time in milliseconds."""
        if not (0 < exposure <= 10000):
            raise ValueError("Exposure must be between 0 and 10000 ms")
        exp_s = exposure / 1000.0
        self._hdcam.dcamprop_setvalue(dc.DCAMIDPROP.DCAM_IDPROP_EXPOSURETIME, exp_s)

    def shape(self) -> tuple[int, ...]:
        """Return the shape of the image buffer."""
        hdcam = self._hdcam
        width = int(hdcam.dcamprop_getvalue(dc.DCAMIDPROP.DCAM_IDPROP_IMAGE_WIDTH))
        height = int(hdcam.dcamprop_getvalue(dc.DCAMIDPROP.DCAM_IDPROP_IMAGE_HEIGHT))
        return (height, width)

    def dtype(self) -> np.dtype:
        """Return the NumPy dtype of the image buffer."""
        pt = self._hdcam.dcamprop_getvalue(dc.DCAMIDPROP.DCAM_IDPROP_IMAGE_PIXELTYPE)
        pixel_type = dc.DCAM_PIXELTYPE(int(pt))
        try:
            return PIXEL_TYPE_TO_DTYPE[pixel_type]
        except KeyError:  # pragma: no cover
            raise NotImplementedError(
                f"unsupported pixel type {pixel_type.name}; only MONO8/16 are handled"
            ) from None

    def start_sequence(
        self,
        n_frames: int,
        get_buffer: Callable[[Sequence[int], DTypeLike], np.ndarray],
    ) -> Iterator[Mapping]:
        """Stream **n_frames** images, yielding a dict per frame as UniMMCore expects."""
        shape, dtype = self.shape(), self.dtype()
        hdcam = self._hdcam
        hdcam.dcambuf_alloc(min(n_frames, 64))  # internal DCAM ring buffer
        hwait = hdcam.dcamwait_open()
        timeout = 2_000  # ms

        # Pre-build the frame descriptor (will update .buf each iteration)
        frame = dc.DCAMBUF_FRAME(
            size=c.sizeof(dc.DCAMBUF_FRAME),
            iFrame=-1,
            buf=None,  # will be assigned per-frame
            rowbytes=shape[1] * dtype.itemsize,
            type=0,
            width=shape[1],
            height=shape[0],
            left=0,
            top=0,
        )

        try:
            hdcam.dcamcap_start(dc.DCAMCAP_START.DCAMCAP_START_SEQUENCE)

            for _ in range(n_frames):
                # wait for HW to have a fresh frame
                hwait.dcamwait_start(
                    dc.DCAMWAIT_EVENT.DCAMWAIT_CAPEVENT_FRAMEREADY,
                    timeout=timeout,  # pyright: ignore
                )

                # get the frame from core
                img = get_buffer(shape, dtype)
                frame.buf = img.ctypes.data_as(c.c_void_p)

                # copy the frame from the DCAM buffer to our buffer
                dc.check_status(
                    dc.dcamapi.dcambuf_copyframe(hdcam.hdcam, c.byref(frame))
                )

                yield {}

        finally:
            # stop & drain
            hdcam.dcamcap_stop()
            try:
                hwait.dcamwait_start(
                    eventmask=dc.DCAMWAIT_EVENT.DCAMWAIT_CAPEVENT_STOPPED,
                    timeout=timeout,  # pyright: ignore
                )
            except dc.DCAMError as exc:  # pragma: no cover
                print(f"[DCAM] warning while stopping capture: {exc}")

            hwait.dcamwait_close()
            hdcam.dcambuf_release()


# --------- Use our custom camera in UniMMCore

core = UniMMCore()
core.loadPyDevice("Camera", HamaCam())
core.initializeDevice("Camera")
core.setCameraDevice("Camera")

core.setExposure(1)

# test FPS
core.startContinuousSequenceAcquisition()
ticks: list = []
while len(ticks) < 50:
    if core.getRemainingImageCount():
        ticks.append(time.perf_counter())
        core.popNextImage()
core.stopSequenceAcquisition()
fps = len(ticks) / (ticks[-1] - ticks[0])
print(f"FPS: {fps}")

try:
    from pymmcore_widgets import ExposureWidget, ImagePreview, LiveButton, SnapButton
    from qtpy.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget

    app = QApplication([])

    window = QWidget()
    window.setWindowTitle("UniCore Camera Example")
    layout = QVBoxLayout(window)

    top = QHBoxLayout()
    top.addWidget(SnapButton(mmcore=core))
    top.addWidget(LiveButton(mmcore=core))
    top.addWidget(ExposureWidget(mmcore=core))
    layout.addLayout(top)
    layout.addWidget(ImagePreview(mmcore=core))
    window.setLayout(layout)
    window.resize(800, 600)
    window.show()
    app.exec()
except Exception:
    print("run `pip install pymmcore-widgets[image] PyQt6` to run the GUI example")
    core.snapImage()
    image = core.getImage()
    print("Image shape:", image.shape)
    print("Image dtype:", image.dtype)
    print("Image data:", image)

core.reset()
