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

dcamapi = dc.dcamapi


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
        if pixel_type == dc.DCAM_PIXELTYPE.DCAM_PIXELTYPE_MONO8:
            return np.dtype(np.uint8)
        elif pixel_type == dc.DCAM_PIXELTYPE.DCAM_PIXELTYPE_MONO16:
            return np.dtype(np.uint16)
        raise NotImplementedError(
            f"Unsupported pixel type: {pixel_type}. Only MONO8 and MONO16 are supported"
        )

    def start_sequence(
        self,
        n: int,
        get_buffer: Callable[[Sequence[int], DTypeLike], np.ndarray],
    ) -> Iterator[Mapping]:
        """Start a sequence acquisition."""
        shape, dtype = self.shape(), self.dtype()

        # stream
        self._hdcam.dcambuf_alloc(min(n, 64))  # DCAM internal ring buffer
        hwait = self._hdcam.dcamwait_open()

        try:
            # 2. Start sequence capture
            self._hdcam.dcamcap_start(dc.DCAMCAP_START.DCAMCAP_START_SEQUENCE)

            for _i in range(n):  # Loop for the number of frames UniMMCore expects
                # 3. Wait for a frame to be ready in DCAM's internal buffer
                # Use DCAMWAIT_CAPEVENT_FRAMEREADY
                hwait.dcamwait_start(
                    eventmask=dc.DCAMWAIT_EVENT.DCAMWAIT_CAPEVENT_FRAMEREADY,
                    timeout=2000,  # Example timeout in ms, adjust as needed
                )

                # 4. Get the destination buffer from UniMMCore (or your calling layer)
                img = get_buffer(shape, dtype)

                # 5. Copy the captured frame into the user's provided buffer
                # You need to construct a DCAMBUF_FRAME structure for dcambuf_copyframe
                frame_params = dc.DCAMBUF_FRAME(
                    size=c.sizeof(dc.DCAMBUF_FRAME),
                    iFrame=-1,  # Request the latest captured image
                    buf=img.ctypes.data_as(c.c_void_p),  # Buffer to copy into
                    rowbytes=img.strides[0],
                    type=0,  #  copy frame
                    width=shape[1],  # Width of the image
                    height=shape[0],  # Height of the image
                    left=0,  # Left offset in the image
                    top=0,  # Top offset in the image
                )

                # Call the dcambuf_copyframe function.
                # This might be available as a method on self._hdcam (e.g., self._hdcam.dcambuf_copyframe(frame_params))
                # or you might need to call the raw API function if pyDCAM doesn't wrap it this way.
                # Assuming pyDCAM's check_status and dcamapi are accessible:
                dc.check_status(
                    dcamapi.dcambuf_copyframe(self._hdcam.hdcam, c.byref(frame_params))
                )

                # Yield metadata or confirmation
                yield {"skipped_frames": 0, "frame_time_us": 0}  # Placeholder

        finally:
            # 6. Stop capture and release resources
            self._hdcam.dcamcap_stop()

            # It's good practice to wait for the STOPPED event to ensure clean termination
            try:
                hwait.dcamwait_start(
                    eventmask=dc.DCAMWAIT_EVENT.DCAMWAIT_CAPEVENT_STOPPED, timeout=1000
                )
            except dc.DCAMError as e:
                # Handle timeout or other errors if necessary, e.g., print a warning
                print(f"Warning/Error waiting for capture to stop: {e}")

            hwait.dcamwait_close()

            # Release the internally allocated DCAM buffers
            self._hdcam.dcambuf_release()


# --------- Use our custom camera in UniMMCore

core = UniMMCore()
core.loadPyDevice("Camera", HamaCam())
core.initializeDevice("Camera")
core.setCameraDevice("Camera")

core.setExposure(50)

# test FPS
core.startContinuousSequenceAcquisition()
ticks: list = []
while len(ticks) < 20:
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
