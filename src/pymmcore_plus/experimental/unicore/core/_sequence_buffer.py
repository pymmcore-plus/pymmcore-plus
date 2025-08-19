"""High-throughput, zero-copy ring buffer for camera image streams."""

from __future__ import annotations

import threading
from collections import deque
from typing import TYPE_CHECKING, Any, NamedTuple

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from numpy.typing import DTypeLike, NDArray


class BufferSlot(NamedTuple):
    """Record describing one frame held in the pool."""

    array: NDArray[Any]
    metadata: Mapping[str, Any] | None  # metadata associated with this frame
    nbytes_total: int  # full span in the pool (data + padding)


# TODO: version that doesn't use contiguous memory,
# but rather uses a deuqe of numpy arrays.
class SequenceStack: ...


class SequenceBuffer:
    """A lock-protected circular buffer backed by a single numpy byte array.

    This buffer is designed for a single device.  If you want to stream data from
    multiple devices, it is recommended to use a separate `SequenceBuffer` for each
    device (rather than to pack two streams into a single FIFO buffer).

    Parameters
    ----------
    size_mb:
        Pool capacity in **mebibytes** (binary - 1 MiB = 1,048,576 bytes).
    overwrite_on_overflow:
        When `True` (default) the oldest frame will be discarded to make space.
        When `False`, an attempt to acquire a slot that does not fit raises
        `BufferError`.
    """

    def __init__(self, size_mb: float, *, overwrite_on_overflow: bool = True) -> None:
        self._size_bytes: int = int(size_mb * 1024 * 1024)
        self._pool: NDArray[np.uint8] = np.empty(self._size_bytes, dtype=np.uint8)

        # ring indices (bytes)
        self._head: int = 0  # next write offset
        self._tail: int = 0  # oldest frame offset
        self._bytes_in_use: int = 0  # live bytes (includes padding)

        # active frames in FIFO order (BufferSlot objects)
        self._slots: deque[BufferSlot] = deque()

        self._overwrite_on_overflow: bool = overwrite_on_overflow
        self._overflow_occurred: bool = False

        self._lock = threading.Lock()  # not re-entrant, but slightly faster than RLock
        self._pending_slot: deque[tuple[NDArray, int]] = deque()

    # ---------------------------------------------------------------------
    # Producer API - acquire a slot, fill it, finalize it
    # ---------------------------------------------------------------------

    def acquire_slot(
        self, shape: Sequence[int], dtype: DTypeLike = np.uint8
    ) -> NDArray[Any]:
        """Return a **writable** view into the internal pool.

        After filling the array, *must* call `finalize_slot`.
        """
        dtype_ = np.dtype(dtype)
        nbytes_data = int(np.prod(shape, dtype=int) * dtype_.itemsize)

        # ---------- NEW: explicit capacity check ---------------------------
        if nbytes_data > self._size_bytes:
            msg = (
                f"Requested size ({nbytes_data} bytes) exceeds buffer capacity "
                f"({self.size_mb} MiB)."
            )
            raise BufferError(msg)

        # --- reserve space -------------------------------------------------

        with self._lock:
            # Calculate padding needed to align start address to dtype boundary
            align_pad = (-self._head) % dtype_.itemsize
            needed = nbytes_data + align_pad

            # ensure capacity (may evict oldest frames if overwrite enabled)
            self._ensure_space(needed)

            # alignment may force wrapping to 0 => recompute alignment
            if needed > self._contiguous_free_bytes:
                # wrap head to start of buffer for contiguous allocation
                self._head = 0
                align_pad = 0  # new head is already aligned to buffer start
                needed = nbytes_data  # recalculated without padding
                self._ensure_space(needed)  # guaranteed to succeed after wrap

            # Calculate actual start position after alignment padding
            start = self._head + align_pad
            # Advance head pointer past this allocation (with wraparound)
            self._head = (start + nbytes_data) % self._size_bytes
            # Track total bytes consumed (data + alignment padding)
            self._bytes_in_use += needed

            # Create zero-copy view into the pool buffer at calculated offset
            arr: NDArray[Any] = np.ndarray(
                shape, dtype_, buffer=self._pool, offset=start
            )
            self._pending_slot.append((arr, needed))
            return arr

    def finalize_slot(self, metadata: Mapping[str, Any] | None = None) -> None:
        """Publish the frame acquired via `acquire_write_slot`.

        This makes the frame available for retrieval via `pop_next` or
        `peek_last`. If `metadata` is provided, it will be merged into the
        slot's metadata dictionary.
        """
        with self._lock:
            if not self._pending_slot:
                msg = "No pending slot to finalize"
                raise RuntimeError(msg)

            arr, nbytes_total = self._pending_slot.popleft()
            self._slots.append(BufferSlot(arr, metadata, nbytes_total))

    # Convenience: copy-in one-shot insert ------------------------------

    def insert_data(
        self, data: NDArray[Any], metadata: Mapping[str, Any] | None = None
    ) -> None:
        """Insert data into the buffer, overwriting any existing frame.

        This is a convenience method that acquires a slot, copies the data, and
        finalizes the slot in one go.

        For users who *can* write directly into our buffer, they should use
        `acquire_slot` and `finalize_slot`. `insert_data` is for when the data already
        exists in another NumPy array.
        """
        self.acquire_slot(data.shape, data.dtype)[:] = data
        self.finalize_slot(metadata)

    # ------------------------------------------------------------------
    # Consumer API - pop frames, peek at frames
    # ------------------------------------------------------------------

    def pop_next(
        self, *, out: np.ndarray | None = None
    ) -> tuple[NDArray[Any], Mapping[str, Any]] | None:
        """Remove and return the oldest frame.

        If `copy` is `True`, a copy of the data is returned, otherwise a read-only
        view into the internal buffer is returned. The metadata is always returned
        as a copy to prevent external modification.
        """
        with self._lock:
            if not self._slots:
                return None
            slot = self._slots.popleft()

        if out is not None:
            out[:] = slot.array
            arr = out
        else:
            arr = slot.array.copy()
        self._evict_slot(slot)

        # return actual metadata, we're done with it.
        return arr, (slot.metadata or {})

    def peek_last(
        self, *, out: np.ndarray | None = None
    ) -> tuple[NDArray[Any], Mapping[str, Any]] | None:
        """Return the newest frame without removing it."""
        return self.peek_nth_from_last(0, out=out)

    def peek_nth_from_last(
        self, n: int, *, out: np.ndarray | None = None
    ) -> tuple[NDArray[Any], dict[str, Any]] | None:
        """Return the n-th most recent frame without removing it.

        Last frame is n=0, second to last is n=1, etc.
        """
        with self._lock:
            if n < 0 or n >= len(self._slots):
                return None
            slot = self._slots[-(n + 1)]
            if out is not None:
                out[:] = slot.array
                arr = out
            else:
                arr = slot.array.copy()

            # Return a copy of the metadata to avoid external modification
            return arr, (dict(slot.metadata) if slot.metadata else {})

    # ------------------------------------------------------------------
    # Administrative helpers
    # ------------------------------------------------------------------

    def clear(self) -> None:
        with self._lock:
            self._slots.clear()
            self._pending_slot.clear()
            self._head = self._tail = self._bytes_in_use = 0
            self._overflow_occurred = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def size_mb(self) -> float:  # human readable
        return self._size_bytes / 1024**2

    @property
    def size_bytes(self) -> int:
        """Return the buffer size in bytes."""
        return self._size_bytes

    @property
    def used_bytes(self) -> int:
        """Return the number of bytes currently in use."""
        return self._bytes_in_use

    @property
    def free_bytes(self) -> int:
        """Return the number of free bytes in the buffer."""
        return self._size_bytes - self._bytes_in_use

    @property
    def free_mb(self) -> float:
        """Get the free space in the buffer in mebibytes."""
        return self.free_bytes / 1024**2

    @property
    def overwrite_on_overflow(self) -> bool:
        """Return the overflow policy (immutable while data is present)."""
        return self._overwrite_on_overflow

    @overwrite_on_overflow.setter
    def overwrite_on_overflow(self, value: bool) -> None:
        """Set the overflow policy (immutable while data is present)."""
        with self._lock:
            if self._bytes_in_use > 0:
                msg = "Cannot change overflow policy with active data in buffer."
                raise RuntimeError(msg)
            self._overwrite_on_overflow = value

    def __len__(self) -> int:
        """Return the number of frames currently in the buffer."""
        return len(self._slots)

    @property
    def overflow_occurred(self) -> bool:
        """Return whether an overflow occurred since the last clear."""
        return self._overflow_occurred

    def __repr__(self) -> str:
        used_mb = self.used_bytes / 1024**2
        name = self.__class__.__name__
        return (
            f"{name}(size_mb={self.size_mb:.1f}, slots={len(self)}, "
            f"used_mb={used_mb:.1f}, overwrite={self._overwrite_on_overflow})"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evict_slot(self, slot: BufferSlot) -> None:
        """Advance the tail pointer past `slot`, updating house-keeping."""
        self._tail = (self._tail + slot.nbytes_total) % self._size_bytes
        self._bytes_in_use -= slot.nbytes_total

    @property
    def _contiguous_free_bytes(self) -> int:
        """Get the number of contiguous free bytes in the buffer."""
        if self._bytes_in_use >= self._size_bytes:
            return 0
        if self._bytes_in_use == 0:
            return self._size_bytes
        if self._head >= self._tail:
            return self._size_bytes - self._head
        # it's very hard to make this case happen...
        return self._tail - self._head  # pragma: no cover

    def _ensure_space(self, needed: int) -> None:
        """Ensure `needed` bytes contiguous space is available."""
        while self._contiguous_free_bytes < needed:
            if not self._slots:
                # Buffer empty but fragmented: just reset pointers
                self._head = self._tail = self._bytes_in_use = 0
                break
            if not self._overwrite_on_overflow:
                self._overflow_occurred = True
                msg = "Buffer is full and overwrite is disabled."
                raise BufferError(msg)
            self._overflow_occurred = True
            while self._slots and self._contiguous_free_bytes < needed:
                slot = self._slots.popleft()
                self._evict_slot(slot)

        # If the buffer is now empty, reset head/tail to maximise contiguous space.
        if self._bytes_in_use == 0:
            self._head = self._tail = 0
