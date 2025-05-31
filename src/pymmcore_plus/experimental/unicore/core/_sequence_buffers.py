from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Protocol

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Mapping


class SequenceBuffer(Protocol):
    running: bool
    buffers: deque[np.ndarray]

    def __init__(
        self, shape: tuple[int, ...], dtype: np.dtype, expected: int | None
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

    This is the simplest implementation, using a deque to hold
    the acquired frames and their metadata.  It is suitable for
    continuous acquisition where the number of frames is not known
    in advance, or when the number of frames is small and manageable.

    Pros:
    O(1) queue ops, no locking needed if only one producer thread; each frame gets
    its own base buffer, so the consumer can keep references for as long as it wants
    without worrying that the producer will overwrite them.

    Cons:
    One malloc/NumPy-object creation per frame.  At tens of frames per sec, that
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
        self, shape: tuple[int, ...], dtype: np.dtype, expected: int | None
    ) -> None:
        self.shape = shape
        self.dtype = dtype
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

    Pros:
    Zero extra allocations after the first one; the slice view itself is a light
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
        self, shape: tuple[int, ...], dtype: np.dtype, expected: int | None
    ) -> None:
        if expected is None:
            raise ValueError("Contiguous-array strategy needs a finite *expected*")

        self.shape = shape
        self.dtype = dtype
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
        dtype: np.dtype,
        expected: int | None,
        *,
        pool: int = 16,  # tune to match your pipeline depth
    ) -> None:
        if pool < 2:
            raise ValueError("pool size must be >= 2")

        self.shape = shape
        self.dtype = dtype
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
        # (done in pop_left() below)

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
