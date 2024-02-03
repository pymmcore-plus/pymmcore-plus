"""OME.TIFF writer for MDASequences.

Borrowed from the pattern shared by Christoph Gohlke:
https://forum.image.sc/t/how-to-create-an-image-series-ome-tiff-from-python/42730/7

Note, these are the valid axis keys tifffile:
Supported by OME-XML
    X : width** (image width)
    Y : height** (image length)
    Z : depth** (image depth)
    S : sample** (color space and extra samples)
    T : time** (time series)
    C : channel** (acquisition path or emission wavelength)
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
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import numpy as np

from ._ome_base import OMEWriterBase

if TYPE_CHECKING:
    from pathlib import Path


class OMETiffWriter(OMEWriterBase[np.memmap]):
    def __init__(self, filename: Path | str) -> None:
        try:
            import tifffile  # noqa: F401
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "tifffile is required to use this handler. "
                "Please `pip install tifffile`."
            ) from e

        self._filename = str(filename)
        if not self._filename.endswith((".ome.tiff", ".ome.tif")):
            raise ValueError("filename must end with '.ome.tiff' or '.ome.tif'")

        super().__init__()

    def write_frame(
        self, ary: np.memmap, index: tuple[int, ...], frame: np.ndarray
    ) -> None:
        super().write_frame(ary, index, frame)
        ary.flush()

    def new_array(
        self, position_key: str, dtype: np.dtype, sizes: dict[str, int]
    ) -> np.memmap:
        from tifffile import imwrite, memmap

        dims, shape = zip(*sizes.items())

        # see tifffile.tiffile for more metadata options
        metadata: dict[str, Any] = {"axes": "".join(dims).upper()}
        if seq := self._current_sequence:
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
        # there's a lot we could still capture, but it comes off the microscope
        # over the course of the acquisition (such as stage positions, exposure times)
        # ... one option is to accumulate these things and then use `tifffile.comment`
        # to update the total metadata in sequenceFinished
        if seq and seq.sizes.get("p", 1) > 1:
            fname = self._filename.replace(".ome.tif", f"_{position_key}.ome.tif")
        else:
            fname = self._filename
        imwrite(fname, shape=shape, dtype=dtype, metadata=metadata)

        # this is a bit of a hack.
        # tifffile.memmap doesn't support 6+D arrays,
        # memory map numpy array to data in OME-TIFF file
        mmap = memmap(fname)
        mmap.shape = shape  # handle singletons?
        return mmap  # type: ignore
