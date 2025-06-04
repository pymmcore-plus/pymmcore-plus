import ctypes as c
from collections.abc import Iterator

import numpy as np
import pyDCAM as dc

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
        dc.check_status(dcamapi.dcambuf_attach(self.hdcam, c.byref(attach)))

    def release_buffer(self, kind: int = 0) -> None:
        """Release the attached buffer."""
        dc.check_status(dcamapi.dcambuf_release(self.hdcam, kind))

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
        hwait.dcamwait_start(timeout=timeout)  # type: ignore[union-attr]
        if out is None:
            # see also: dcambuf_lockframe
            out = self.dcambuf_copyframe()
        self.dcambuf_release()
        self.dcamcap_stop()
        return out

    def copy_into(self, img: np.ndarray) -> None:
        """Copy device dcambuf_alloc buffer into img."""
        height, width = img.shape
        rb = self.dcamprop_getvalue(dc.DCAMIDPROP.DCAM_IDPROP_IMAGE_ROWBYTES)
        frame = dc.DCAMBUF_FRAME(
            size=c.sizeof(dc.DCAMBUF_FRAME),
            iFrame=-1,  # -1 means latest frame
            width=width,
            height=height,
            left=0,
            top=0,
            buf=img.ctypes.data,
            rowbytes=int(rb),
        )
        dc.check_status(dcamapi.dcambuf_copyframe(self.hdcam, c.byref(frame)))

    def stream(self, num: int) -> Iterator[np.ndarray]:
        """Stream images from the camera."""
        self.dcamcap_start(dc.DCAMCAP_START.DCAMCAP_START_SEQUENCE)
        for _ in range(num):
            self.dcamwait_open().dcamwait_start()
            img = np.empty(self.shape(), dtype=self.dtype(), order="C")
            yield img
            self.release_buffer()
        self.dcamcap_stop()


with dc.use_dcamapi:
    with HDCAM() as hdcam:
        img1 = hdcam.snap()
        img2 = np.empty(hdcam.shape(), dtype=hdcam.dtype(), order="C")
        hdcam.snap(img2)

        print(img1.mean())
        print(img2.mean())
        hdcam.release_buffer()
