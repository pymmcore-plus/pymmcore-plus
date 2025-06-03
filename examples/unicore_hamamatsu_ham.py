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
            iKind=0,
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

    def stream(self, num: int) -> Iterator[np.ndarray]:
        """Stream images from the camera."""
        self.dcamcap_start(dc.DCAMCAP_START.DCAMCAP_START_SEQUENCE)
        for _ in range(num):
            self.dcamwait_open().dcamwait_start()
            img = np.empty(self.shape(), dtype=self.dtype(), order="C")
            yield img
            self.dcambuf_release()
        self.dcamcap_stop()


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
        shape, dtype = self.shape(), self.dtype()
        for _ in range(n):
            buf = get_buffer(shape, dtype)
            self._hdcam.snap(buf)
            yield {}


core = UniMMCore()
core.loadPyDevice("Camera", HamaCam())
core.initializeDevice("Camera")
core.setCameraDevice("Camera")

core.setExposure(42)


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
