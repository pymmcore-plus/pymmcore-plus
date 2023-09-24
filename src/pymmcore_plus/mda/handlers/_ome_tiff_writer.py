"""OME.TIFF writer for MDASequences.

Borrowed from the pattern shared by Christoph Gohlke:
https://forum.image.sc/t/how-to-create-an-image-series-ome-tiff-from-python/42730/7
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from pathlib import Path

    import numpy as np
    import useq


class OMETiffWriter:
    def __init__(self, filename: Path | str) -> None:
        try:
            import tifffile  # noqa: F401
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "tifffile is required to use this handler. "
                "Please `pip install tifffile`."
            ) from e

        # create an empty OME-TIFF file
        self._filename = filename
        self._mmap: None | np.memmap = None

    def sequenceStarted(self, seq: useq.MDASequence) -> None:
        self._set_sequence(seq)

    def frameReady(self, frame: np.ndarray, event: useq.MDAEvent, meta: dict) -> None:
        if self._mmap is None:
            if not self._current_sequence:
                # just in case sequenceStarted wasn't called
                self._set_sequence(event.sequence)  # pragma: no cover

            if not (seq := self._current_sequence):
                raise NotImplementedError(
                    "Writing zarr without a MDASequence not yet implemented"
                )

            mmap = self._create_seq_memmap(frame, seq, meta)
        else:
            mmap = self._mmap

        # WRITE DATA TO DISK
        index = tuple(event.index.get(k) for k in self._used_axes)
        mmap[index] = frame
        mmap.flush()

    # -------------------- private --------------------

    def _set_sequence(self, seq: useq.MDASequence | None) -> None:
        """Set the current sequence, and update the used axes."""
        self._current_sequence = seq
        if seq:
            self._used_axes = tuple(seq.used_axes)

    def _create_seq_memmap(
        self, frame: np.ndarray, seq: useq.MDASequence, meta: dict
    ) -> np.memmap:
        from tifffile import imwrite, memmap

        shape = (
            *tuple(v for k, v in seq.sizes.items() if k in self._used_axes),
            *frame.shape,
        )
        axes = (*self._used_axes, "y", "x")
        dtype = frame.dtype

        # see tifffile.tiffile for more metadata options
        metadata: dict[str, Any] = {"axes": "".join(axes).upper()}
        if seq:
            if seq.time_plan and hasattr(seq.time_plan, "interval"):
                interval = seq.time_plan.interval
                if isinstance(interval, timedelta):
                    interval = interval.total_seconds()
                metadata["TimeIncrement"] = interval
                metadata["TimeIncrementUnit"] = "s"
            if seq.z_plan and hasattr(seq.z_plan, "step"):
                metadata["PhysicalSizeZ"] = seq.z_plan.step
                metadata["PhysicalSizeZUnit"] = "µm"
            if seq.channels:
                metadata["Channel"] = {"Name": [c.config for c in seq.channels]}
        if acq_date := meta.get("Time"):
            metadata["AcquisitionDate"] = acq_date
        if pix := meta.get("PixelSizeUm"):
            metadata["PhysicalSizeX"] = pix
            metadata["PhysicalSizeY"] = pix
            metadata["PhysicalSizeXUnit"] = "µm"
            metadata["PhysicalSizeYUnit"] = "µm"

        # TODO:
        # there's a lot we could still capture, but it comes off the microscope
        # over the course of the acquisition (such as stage positions, exposure times)
        # ... one option is to accumulate these things and then use `tifffile.comment`
        # to update the total metadata in sequenceFinished
        imwrite(self._filename, shape=shape, dtype=dtype, metadata=metadata)

        # memory map numpy array to data in OME-TIFF file
        self._mmap = memmap(self._filename)
        return cast("np.memmap", self._mmap)
