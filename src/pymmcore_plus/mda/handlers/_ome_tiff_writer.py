"""OME.TIFF writer for MDASequences.

Borrowed from the pattern shared by Christoph:
https://forum.image.sc/t/how-to-create-an-image-series-ome-tiff-from-python/42730/7

Note, these are the valid axis keys tifffile:
Supported by OME-XML
    X : width** (image width)
    Y : height** (image length)
    Z : depth** (image depth)
    T : time** (time series)
    C : channel** (acquisition path or emission wavelength)
    Modulo axes:
    S : sample** (color space and extra samples)
    A : angle** (OME)
    P : phase** (OME. In LSM, **P** maps to **position**)
    R : tile** (OME. Region, position, or mosaic)
    H : lifetime** (OME. Histogram)
    E : lambda** (OME. Excitation wavelength)
    Q : other** (OME)
Not Supported by OME-XML
    I : sequence** (generic sequence of images, frames, planes, pages)
    L : exposure** (FluoView)
    V : event** (FluoView)
    M : mosaic** (LSM 6)

Rules:
- all axes must be one of TZCYXSAPRHEQ
- len(axes) must equal len(shape)
- dimensions (order) must end with YX or YXS
- no axis can be repeated
- no more than 8 dimensions (or 9 if 'S' is included)

Non-OME (ImageJ) hyperstack axes MUST be in TZCYXS order
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import numpy as np

from ._5d_writer_base import _NULL, _5DWriterBase

if TYPE_CHECKING:
    from pathlib import Path

    import useq

    from pymmcore_plus.metadata import SummaryMetaV1

IMAGEJ_AXIS_ORDER = "tzcyxs"


class OMETiffWriter(_5DWriterBase[np.memmap]):
    """MDA handler that writes to a 5D OME-TIFF file.

    Positions will be split into different files.

    Data is memory-mapped to disk using numpy.memmap via tifffile.  Tifffile handles
    the OME-TIFF format.

    Parameters
    ----------
    filename : Path | str
        The filename to write to.  Must end with '.ome.tiff' or '.ome.tif'.
    """

    def __init__(self, filename: Path | str) -> None:
        try:
            import tifffile  # noqa: F401
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "tifffile is required to use this handler. "
                "Please `pip install tifffile`."
            ) from e

        self._filename = str(filename)
        if not self._filename.endswith((".tiff", ".tif")):  # pragma: no cover
            raise ValueError("filename must end with '.tiff' or '.tif'")
        self._is_ome = ".ome.tif" in self._filename

        super().__init__()

    def sequenceStarted(
        self, seq: useq.MDASequence, meta: SummaryMetaV1 | object = _NULL
    ) -> None:
        super().sequenceStarted(seq, meta)
        # Non-OME (ImageJ) hyperstack axes MUST be in TZCYXS order
        # so we reorder the ordered position_sizes dicts.  This will ensure
        # that the array indices created from event.index are in the correct order.
        if not self._is_ome:
            self._position_sizes = [
                {k: x[k] for k in IMAGEJ_AXIS_ORDER if k.lower() in x}
                for x in self.position_sizes
            ]

    def write_frame(
        self, ary: np.memmap, index: tuple[int, ...], frame: np.ndarray
    ) -> None:
        """Write a frame to the file."""
        super().write_frame(ary, index, frame)
        ary.flush()

    def new_array(
        self, position_key: str, dtype: np.dtype, sizes: dict[str, int]
    ) -> np.memmap:
        """Create a new tifffile file and memmap for this position."""
        from tifffile import imwrite, memmap

        dims, shape = zip(*sizes.items())

        metadata: dict[str, Any] = self._sequence_metadata()
        metadata["axes"] = "".join(dims).upper()

        # append the position key to the filename if there are multiple positions
        if (seq := self.current_sequence) and seq.sizes.get("p", 1) > 1:
            ext = ".ome.tif" if self._is_ome else ".tif"
            fname = self._filename.replace(ext, f"_{position_key}{ext}")
        else:
            fname = self._filename

        # create parent directories if they don't exist
        # Path(fname).parent.mkdir(parents=True, exist_ok=True)
        # write empty file to disk
        imwrite(
            fname,
            shape=shape,
            dtype=dtype,
            metadata=metadata,
            imagej=not self._is_ome,
            ome=self._is_ome,
        )

        # memory-mapped NumPy array of image data stored in TIFF file.
        mmap = memmap(fname, dtype=dtype)
        # This line is important, as tifffile.memmap appears to lose singleton dims
        mmap.shape = shape

        return mmap  # type: ignore

    def _sequence_metadata(self) -> dict:
        """Create metadata for the sequence, when creating a new file."""
        if not self._is_ome:
            return {}

        metadata: dict = {}
        # see tifffile.tifffile for more metadata options
        if seq := self.current_sequence:
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

        # TODO
        # if acq_date := meta.get("Time"):
        #     metadata["AcquisitionDate"] = acq_date
        # if pix := meta.get("PixelSizeUm"):
        #     metadata["PhysicalSizeX"] = pix
        #     metadata["PhysicalSizeY"] = pix
        #     metadata["PhysicalSizeXUnit"] = "µm"
        #     metadata["PhysicalSizeYUnit"] = "µm"

        # TODO:
        # there's a LOT we could still capture, but it comes off the microscope
        # over the course of the acquisition (such as stage positions, exposure times)
        # ... one option is to accumulate these things and then use `tifffile.comment`
        # to update the total metadata in finalize_metadata
        return metadata
