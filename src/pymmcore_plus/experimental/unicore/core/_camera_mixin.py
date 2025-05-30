from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Protocol,
    cast,
    overload,
)

import numpy as np
from numpy.typing import DTypeLike

from pymmcore_plus.core import Keyword as KW
from pymmcore_plus.core._metadata import Metadata

from ._base_mixin import UniCoreBase

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.typing import DTypeLike
    from pymmcore import DeviceLabel

    from pymmcore_plus.experimental.unicore.devices._camera import Camera


class SequenceBuffer(Protocol):
    running: bool
    buffers: deque[np.ndarray]

    def __init__(
        self, shape: tuple[int, ...], dtype: DTypeLike, expected: int | None
    ) -> None: ...

    # ---------- required call-backs for the Camera ---------------------

    def get_buffer(self) -> np.ndarray:
        """Return a new empty buffer for the next image."""
        ...

    def notify(self, meta: Mapping) -> None:
        """Notify that a new image has been acquired, passing metadata."""
        ...

    def pop_left(self) -> tuple[np.ndarray, Mapping] | None:
        """Pop the next image and its metadata from the left (FIFO)."""
        ...

    def __len__(self) -> int:
        """Return the number of available (filled) buffers.  Used for bool too."""
        ...


class SeqState(SequenceBuffer):
    """Object to hold state for a sequence acquisition.

    Pros: O(1) queue ops, no locking needed if only one producer thread; each frame gets
    its own base buffer, so the consumer can keep references for as long as it wants
    without worrying that the producer will overwrite them.

    Cons: One malloc/NumPy-object creation per frame.  At tens of frames per sec, that
    cost is likely negligible (< 50 µs / frame on CPython 3.12).  It may start to matter
    when you push hundreds of 2-10 MB frames per second.
    """

    __slots__ = (
        "acquired",
        "buffers",
        "dtype",
        "expected",
        "metadata",
        "pending",
        "running",
        "shape",
    )

    def __init__(
        self, shape: tuple[int, ...], dtype: DTypeLike, expected: int | None
    ) -> None:
        self.shape = shape
        self.dtype = np.dtype(dtype)
        self.buffers: deque[np.ndarray] = deque()
        self.metadata: deque[Mapping] = deque()
        self.pending: deque[np.ndarray] = deque()
        self.running: bool = True
        self.expected = expected
        self.acquired = 0

    def get_buffer(self) -> np.ndarray:
        """Get a new empty buffer for the next image."""
        buf = np.empty(self.shape, dtype=self.dtype)
        self.pending.append(buf)
        return buf

    def notify(self, meta: Mapping) -> None:
        if not self.pending:
            raise RuntimeError("notify() called more times than get_buffer()")

        buf = self.pending.popleft()
        self.buffers.append(buf)
        self.metadata.append(dict(meta))
        self.acquired += 1

        if self.expected is not None and self.acquired >= self.expected:
            self.running = False

    def pop_left(self) -> tuple[np.ndarray, Mapping] | None:
        if not self.buffers:
            return None
        buf = self.buffers.popleft()
        meta = self.metadata.popleft() if self.metadata else {}
        return buf, meta

    def __len__(self) -> int:
        return len(self.buffers)


class SeqStateContiguous(SequenceBuffer):
    """Store every frame in a single pre-allocated 4-D array.

    Requires *expected* (n_frames) to be known and modest in size (e.g. ≤ 10^3 frames of
    < ~20 MB each, or RAM use gets silly).

    Pros: Zero extra allocations after the first one; the slice view itself is a light
    PyObject.  Great when the exact number of frames (N) is known in advance and is
    modest (e.g. 1k images x 2 MP x uint16 ≈ 4 GB).

    Cons:
    Up-front RAM spike. For continuous capture you must guess an upper bound or
    implement your own ring-buffer logic. The camera must not overwrite slot `i` before
    the consumer is done with it → requires a “slot in-use” bookkeeping structure
    anyway. A strided slice is only contiguous if the first axis is the fastest-changing
    in memory (NumPy default), so you need to make sure your camera SDK does a single
    contiguous write or is OK with strides.
    """

    __slots__ = (
        "_array",
        "_next",
        "acquired",
        "buffers",
        "dtype",
        "expected",
        "metadata",
        "pending",
        "running",
        "shape",
    )

    def __init__(
        self, shape: tuple[int, ...], dtype: DTypeLike, expected: int | None
    ) -> None:
        if expected is None:
            raise ValueError("Contiguous-array strategy needs a finite *expected*")

        self.shape = shape
        self.dtype = np.dtype(dtype)
        self.expected = expected

        # allocate (N, H, W[, C])
        self._array = np.empty(expected, dtype=(self.dtype, shape))
        self._next = 0  # write pointer

        self.pending: deque[np.ndarray] = deque()
        self.buffers: deque[np.ndarray] = deque()
        self.metadata: deque[Mapping] = deque()
        self.running = True
        self.acquired = 0

    # ---------------------------------------------------------------- public API

    def get_buffer(self) -> np.ndarray:
        if self._next >= self.expected:
            raise RuntimeError("Camera requested more frames than pre-allocated")
        buf = self._array[self._next]  # view, no copy
        self._next += 1
        self.pending.append(buf)
        return buf  # type: ignore[no-any-return]

    def notify(self, meta: Mapping) -> None:
        if not self.pending:
            raise RuntimeError("notify() called more times than get_buffer()")

        buf = self.pending.popleft()
        self.buffers.append(buf)  # view is still valid
        self.metadata.append(dict(meta))
        self.acquired += 1

        if self.acquired >= self.expected:
            self.running = False

    def pop_left(self) -> tuple[np.ndarray, Mapping] | None:
        if not self.buffers:
            return None
        buf = self.buffers.popleft()
        meta = self.metadata.popleft() if self.metadata else {}
        return buf, meta

    def __len__(self) -> int:
        return len(self.buffers)


class SeqStateRingPool(SequenceBuffer):
    """Circular pool of pre-allocated frame buffers.

    Good when the camera can outrun Python allocation but you don't want
    unbounded RAM growth.  *pool* must exceed the max “frames in flight”
    (camera → host latency).

    Pros:
    Avoids both repeated malloc and the overwrite-while-referenced problem.  You
    pre-allocate, say, 8-to-32 frame buffers and hand them out in a cycle; each slot
    becomes available again when the consumer drops its reference.

    Cons:
    Slightly more bookkeeping than the deque (basically two deques: free and ready).
    The pool size must exceed max_frames_in_flight or you'll stall the camera thread for
    lack of buffers.
    """

    __slots__ = (
        "_free",
        "acquired",
        "buffers",
        "dtype",
        "expected",
        "metadata",
        "pending",
        "running",
        "shape",
    )

    def __init__(
        self,
        shape: tuple[int, ...],
        dtype: DTypeLike,
        expected: int | None,
        *,
        pool: int = 16,  # tune to match your pipeline depth
    ) -> None:
        if pool < 2:
            raise ValueError("pool size must be >= 2")

        self.shape = shape
        self.dtype = np.dtype(dtype)
        self.expected = expected  # may be None for continuous acquisition

        # pre-allocate pool
        self._free: deque[np.ndarray] = deque(
            np.empty(shape, dtype=self.dtype) for _ in range(pool)
        )
        self.pending: deque[np.ndarray] = deque()
        self.buffers: deque[np.ndarray] = deque()
        self.metadata: deque[Mapping] = deque()

        self.running = True
        self.acquired = 0

    # ---------------------------------------------------------------- public API

    def get_buffer(self) -> np.ndarray:
        if not self._free:
            raise BufferError("No free buffer - pool exhausted; enlarge *pool*")

        buf = self._free.popleft()
        self.pending.append(buf)
        return buf

    def notify(self, meta: Mapping) -> None:
        if not self.pending:
            raise RuntimeError("notify() called more times than get_buffer()")

        buf = self.pending.popleft()
        self.buffers.append(buf)
        self.metadata.append(dict(meta))
        self.acquired += 1

        if self.expected is not None and self.acquired >= self.expected:
            self.running = False

        # recycle slot back to free-list once consumer is done
        # (consumer will call recycle() - see below)

    # ---------------------------------------------------------------- consumer hook

    def pop_left(self) -> tuple[np.ndarray, Mapping] | None:
        if not self.buffers:
            return None
        buf = self.buffers.popleft()
        meta = self.metadata.popleft() if self.metadata else {}

        # recycle the slot so the producer can reuse it
        self._free.append(buf)
        return buf, meta

    def __len__(self) -> int:
        return len(self.buffers)


class PyCameraMixin(UniCoreBase):
    """Overrides MMCore camera calls when the device is a Python adapter."""

    # attributes created on-demand
    _current_image_buffer: np.ndarray | None = None
    _seq: SequenceBuffer | None = None

    # --------------------------------------------------------------------- utils

    def _py_camera(self, cameraLabel: str | None = None) -> Camera | None:
        """Return the *Python* Camera for ``label`` (or current), else ``None``."""
        label = cameraLabel or self.getCameraDevice()
        if label in self._pydevices:
            return cast("Camera", self._pydevices[label])
        return None

    def setCameraDevice(self, cameraLabel: DeviceLabel | str) -> None:
        """Set the camera device."""
        label = self._set_current_if_pydevice(KW.CoreCamera, cameraLabel)
        super().setCameraDevice(label)

    def getCameraDevice(self) -> DeviceLabel | Literal[""]:
        """Returns the label of the currently selected camera device.

        Returns empty string if no camera device is selected.
        """
        return self._pycore.current(KW.CoreCamera) or super().getCameraDevice()

    # --------------------------------------------------------------------- snap

    def snapImage(self) -> None:
        if (cam := self._py_camera()) is None:  # fall back to C++
            return super().snapImage()

        shape, dtype = cam.shape(), cam.dtype()
        buf = np.empty(shape, dtype=dtype)
        self._current_image_buffer = buf

        cam.start_sequence(
            1,
            get_buffer=lambda: buf,
            notify=lambda _meta: None,
        )

    # --------------------------------------------------------------------- getImage

    @overload
    def getImage(self, *, fix: bool = True) -> np.ndarray: ...
    @overload
    def getImage(self, numChannel: int, *, fix: bool = True) -> np.ndarray: ...

    def getImage(
        self, numChannel: int | None = None, *, fix: bool = True
    ) -> np.ndarray:
        if (cam := self._py_camera()) is None:
            return (
                super().getImage(numChannel)
                if numChannel is not None
                else super().getImage()
            )

        if self._current_image_buffer is None:
            shape, dtype = cam.shape(), cam.dtype()
            self._current_image_buffer = np.zeros(shape, dtype=dtype)

        return self._current_image_buffer

    # ---------------------------------------------------------------- sequence common

    def _start_sequence(self, cam: Camera, n_images: int | None) -> None:
        """Initialise _seq state and call cam.start_sequence."""
        self._seq = _seq = SeqState(cam.shape(), cam.dtype(), n_images)
        # TODO: should we use None or a large number
        cam.start_sequence(n_images or 2**63 - 1, _seq.get_buffer, _seq.notify)

    # ------------------------------------------------------- startSequenceAcquisition

    @overload
    def startSequenceAcquisition(
        self, numImages: int, intervalMs: float, stopOnOverflow: bool
    ) -> None: ...

    @overload
    def startSequenceAcquisition(
        self,
        cameraLabel: DeviceLabel | str,
        numImages: int,
        intervalMs: float,
        stopOnOverflow: bool,
    ) -> None: ...

    def startSequenceAcquisition(self, *args: Any, **kw: Any) -> None:
        if len(args) == 3:  # current camera
            n, _interval, _stop = args
            if (cam := self._py_camera()) is None:
                return super().startSequenceAcquisition(*args, **kw)

            self._start_sequence(cam, n)

        elif len(args) == 4:  # explicit camera label
            label, n, _interval, _stop = args
            if (cam := self._py_camera(label)) is None:
                return super().startSequenceAcquisition(*args, **kw)

            self.setCameraDevice(label)
            self._start_sequence(cam, n)
        else:
            return super().startSequenceAcquisition(*args, **kw)

    # ------------------------------------------------------ continuous acquisition

    def startContinuousSequenceAcquisition(self, intervalMs: float = 0) -> None:
        if (cam := self._py_camera()) is None:
            return super().startContinuousSequenceAcquisition(intervalMs)

        self._start_sequence(cam, None)

    # ---------------------------------------------------------------- stopSequence

    def stopSequenceAcquisition(self, cameraLabel: str | None = None) -> None:
        if (cam := self._py_camera(cameraLabel)) is None:
            return super().stopSequenceAcquisition()

        cam.stop_sequence()
        if self._seq:
            self._seq.running = False

    # ------------------------------------------------------------------ queries
    @overload
    def isSequenceRunning(self) -> bool: ...
    @overload
    def isSequenceRunning(self, cameraLabel: DeviceLabel | str) -> bool: ...
    def isSequenceRunning(self, cameraLabel: DeviceLabel | str | None = None) -> bool:
        if self._py_camera(cameraLabel) is None:
            return super().isSequenceRunning()

        return bool(self._seq is not None and self._seq.running)

    def getRemainingImageCount(self) -> int:
        if self._py_camera() is None:
            return super().getRemainingImageCount()
        return len(self._seq) if self._seq is not None else 0

    def getLastImage(self) -> np.ndarray:
        if self._py_camera() is None:
            return super().getLastImage()
        if not (self._seq):
            raise IndexError("Circular buffer is empty.")
        return self._seq.buffers[-1]

    # ---------------------------------------------------- popNext helpers

    def popNextImage(self, *, fix: bool = True) -> np.ndarray:
        if self._py_camera() is None:
            return super().popNextImage(fix=fix)
        if not self._seq or not (data := self._seq.pop_left()):
            raise IndexError("Circular buffer is empty.")
        return data[0]

    def popNextImageAndMD(
        self, channel: int = 0, slice: int = 0, *, fix: bool = True
    ) -> tuple[np.ndarray, Metadata]:
        if self._py_camera() is None:
            return super().popNextImageAndMD(channel, slice, fix=fix)
        if not self._seq or not (data := self._seq.pop_left()):
            raise IndexError("Circular buffer is empty.")
        img, md = data
        return (img, Metadata(md))

    # ----------------------------------------------------------------- image info

    def _shape_dtype(self) -> tuple[tuple[int, ...], np.dtype]:
        if (cam := self._py_camera()) is None:
            raise RuntimeError("Called _shape_dtype with C++ camera")
        return cam.shape(), np.dtype(cam.dtype())

    def getImageBitDepth(self) -> int:
        if (cam := self._py_camera()) is None:
            return super().getImageBitDepth()
        dtype = np.dtype(cam.dtype())
        return dtype.itemsize * 8

    def getImageBufferSize(self) -> int:
        if (cam := self._py_camera()) is None:
            return super().getImageBufferSize()
        shape, dtype = cam.shape(), np.dtype(cam.dtype())
        return int(np.prod(shape) * dtype.itemsize)

    def getImageHeight(self) -> int:
        if (cam := self._py_camera()) is None:
            return super().getImageHeight()
        return cam.shape()[0]

    def getImageWidth(self) -> int:
        if (cam := self._py_camera()) is None:
            return super().getImageWidth()
        return cam.shape()[1]

    def getNumberOfComponents(self) -> int:
        if (cam := self._py_camera()) is None:
            return super().getNumberOfComponents()
        shape = cam.shape()
        return 1 if len(shape) == 2 else shape[2]

    def getNumberOfCameraChannels(self) -> int:
        if self._py_camera() is None:
            return super().getNumberOfCameraChannels()
        raise NotImplementedError(
            "getNumberOfCameraChannels is not implemented for Python cameras."
        )

    def getCameraChannelName(self, channelNr: int) -> str:
        """Get the name of the camera channel."""
        if self._py_camera() is None:
            return super().getCameraChannelName(channelNr)
        raise NotImplementedError(
            "getCameraChannelName is not implemented for Python cameras."
        )
