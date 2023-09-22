"""OME.TIFF writer for MDASequences.

Borrowed from the pattern shared by Christoph Gohlke:
https://forum.image.sc/t/how-to-create-an-image-series-ome-tiff-from-python/42730/7
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import numpy as np
    import useq


class OMETiffWriter:
    def __init__(self, filename: str) -> None:
        try:
            import tifffile  # noqa: F401
        except ImportError as e:
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
                self._set_sequence(event.sequence)

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
            self._used_axes = tuple(x for x in seq.used_axes if x != "p")

    def _create_seq_memmap(
        self, frame: np.ndarray, seq: useq.MDASequence, meta: dict
    ) -> np.memmap:
        from tifffile import imwrite, memmap

        shape = (*tuple(v for k, v in seq.sizes.items() if k != "p"), *frame.shape)
        axes = (*(k for k in seq.sizes if k != "p"), "y", "x")
        dtype = frame.dtype
        pixelsize = 1

        # see tifffile.tiffile for more metadata options

        metadata = {
            "axes": "".join(axes).upper(),
            "SignificantBits": 12,
            "TimeIncrement": 0.1,
            "TimeIncrementUnit": "s",
            "PhysicalSizeX": pixelsize,
            "PhysicalSizeXUnit": "µm",
            "PhysicalSizeY": pixelsize,
            "PhysicalSizeYUnit": "µm",
            # "Channel": {"Name": ["Channel 1", "Channel 2"]},
            # "Plane": {"PositionX": [0.0] * 16, "PositionXUnit": ["µm"] * 16},
        }

        imwrite(self._filename, shape=shape, dtype=dtype, metadata=metadata)

        # memory map numpy array to data in OME-TIFF file
        self._mmap = memmap(self._filename)
        return cast("np.memmap", self._mmap)
