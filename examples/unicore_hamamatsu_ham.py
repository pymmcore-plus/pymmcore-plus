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


class _DCAMBUF_ATTACH(c.Structure):
    _fields_ = (
        ("size", c.c_int32),
        ("iKind", c.c_int32),
        ("buffer", c.POINTER(c.c_void_p)),
        ("buffercount", c.c_int32),
    )

# ----- small helper subclass for HDCAM, to facilitate shape/dtype/acquisition

class HDCAM(dc.HDCAM):
    """Subclass of dc.HDCAM to add convenience methods."""

    def dcamcap_status(self) -> dc.DCAMCAP_STATUS:
        """Return the current capture status of the camera."""
        iStatus = c.c_int32(0)
        dc.check_status(dcamapi.dcamcap_status(self.hdcam, c.byref(iStatus)))
        return dc.DCAMCAP_STATUS(iStatus.value)  # bug upstream, doesn't use value

    def shape(self) -> tuple[int, ...]:
        """Return the shape of the image buffer."""
        width = int(self.dcamprop_getvalue(dc.DCAMIDPROP.DCAM_IDPROP_IMAGE_WIDTH))
        height = int(self.dcamprop_getvalue(dc.DCAMIDPROP.DCAM_IDPROP_IMAGE_HEIGHT))
        return (height, width)

    def dtype(self) -> np.dtype:
        """Return the NumPy dtype of the image buffer."""
        pixel_type = dc.DCAM_PIXELTYPE(
            int(self.dcamprop_getvalue(dc.DCAMIDPROP.DCAM_IDPROP_IMAGE_PIXELTYPE))
        )
        if pixel_type == dc.DCAM_PIXELTYPE.DCAM_PIXELTYPE_MONO8:
            return np.dtype(np.uint8)
        elif pixel_type == dc.DCAM_PIXELTYPE.DCAM_PIXELTYPE_MONO16:
            return np.dtype(np.uint16)
        raise NotImplementedError(
            f"Unsupported pixel type: {pixel_type}. Only MONO8 and MONO16 are supported"
        )

    def attach_buffer(self, img: np.ndarray) -> None:
        """Attach a preallocated NumPy array to the camera buffer."""
        ptr_array = (c.c_void_p * 1)()
        ptr_array[0] = c.c_void_p(img.ctypes.data)
        attach = _DCAMBUF_ATTACH(
            size=c.sizeof(_DCAMBUF_ATTACH),
            iKind=0, # DCAMBUF_ATTACHKIND_FRAME
            buffer=ptr_array,
            buffercount=1,
        )
        while self.dcamcap_status() == dc.DCAMCAP_STATUS.DCAMCAP_STATUS_BUSY:
            print("Waiting for camera to be ready...", self.dcamcap_status().name)
            time.sleep(0.1)
        dc.check_status(dcamapi.dcambuf_attach(self.hdcam, c.byref(attach)))

    def snap(
        self,
        out: np.ndarray | None = None,
        *,
        timeout: int = 2000,
    ) -> np.ndarray:
        """Snap into the attached buffer."""
        if out is None:
            self.dcambuf_alloc(1)
        else:
            self.attach_buffer(out)
        hwait = self.dcamwait_open()
        self.dcamcap_start(dc.DCAMCAP_START.DCAMCAP_START_SNAP)
        hwait.dcamwait_start(timeout=timeout)
        if out is None:
            # see also: dcambuf_lockframe
            out = self.dcambuf_copyframe()
        self.dcambuf_release()
        self.dcamcap_stop()
        hwait.dcamwait_start(
            dc.DCAMWAIT_EVENT.DCAMWAIT_CAPEVENT_STOPPED, timeout=timeout
        )
        return out


# -------- Here is our actual Device Adaptor for pymmcore_plus.unicore.Camera

class HamaCam(Camera):
    def initialize(self) -> None:
        """Initialize the camera."""
        if count := dc.dcamapi_init():
            print(f"DCAM API initialized. Found {count} devices.")
        else:
            raise RuntimeError("Failed to initialize DCAM API")

        self._hdcam = HDCAM()

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
        return self._hdcam.shape()

    def dtype(self) -> DTypeLike:
        """Return the data type of the image buffer."""
        return self._hdcam.dtype()

    def start_sequence(
        self,
        n: int,
        get_buffer: Callable[[Sequence[int], DTypeLike], np.ndarray],
    ) -> Iterator[Mapping]:
        """Start a sequence acquisition."""
        shape, dtype = self._hdcam.shape(), self._hdcam.dtype()

        # stream
        self._hdcam.dcambuf_alloc(min(n, 64))  # DCAM internal ring buffer
        hwait = self._hdcam.dcamwait_open()

        try:
            
            # 2. Start sequence capture
            self._hdcam.dcamcap_start(dc.DCAMCAP_START.DCAMCAP_START_SEQUENCE)

            for _i in range(n): # Loop for the number of frames UniMMCore expects
                # 3. Wait for a frame to be ready in DCAM's internal buffer
                # Use DCAMWAIT_CAPEVENT_FRAMEREADY
                hwait.dcamwait_start(
                    eventmask=dc.DCAMWAIT_EVENT.DCAMWAIT_CAPEVENT_FRAMEREADY,
                    timeout=2000  # Example timeout in ms, adjust as needed
                )

                # 4. Get the destination buffer from UniMMCore (or your calling layer)
                img = get_buffer(shape, dtype)

                # 5. Copy the captured frame into the user's provided buffer
                # You need to construct a DCAMBUF_FRAME structure for dcambuf_copyframe
                frame_params = dc.DCAMBUF_FRAME(
                    size=c.sizeof(dc.DCAMBUF_FRAME),
                    iFrame = -1,  # Request the latest captured image
                    buf = img.ctypes.data_as(c.c_void_p),  # Buffer to copy into
                    rowbytes = img.strides[0],
                    type = 0,  #  copy frame
                    width = shape[1],  # Width of the image
                    height = shape[0],  # Height of the image
                    left = 0,  # Left offset in the image
                    top = 0,  # Top offset in the image
                )


                # Call the dcambuf_copyframe function.
                # This might be available as a method on self._hdcam (e.g., self._hdcam.dcambuf_copyframe(frame_params))
                # or you might need to call the raw API function if pyDCAM doesn't wrap it this way.
                # Assuming pyDCAM's check_status and dcamapi are accessible:
                dc.check_status(
                    dcamapi.dcambuf_copyframe(self._hdcam.hdcam, c.byref(frame_params))
                )

                # Yield metadata or confirmation
                yield {"skipped_frames": 0, "frame_time_us": 0} # Placeholder

        finally:
            # 6. Stop capture and release resources
            self._hdcam.dcamcap_stop()
            

            # It's good practice to wait for the STOPPED event to ensure clean termination
            try:
                hwait.dcamwait_start(
                    eventmask=dc.DCAMWAIT_EVENT.DCAMWAIT_CAPEVENT_STOPPED, 
                    timeout=1000 
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
