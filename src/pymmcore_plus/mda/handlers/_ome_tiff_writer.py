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

import warnings
from typing import TYPE_CHECKING

import numpy as np
from ome_types.model import OME

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
        self, position_key: str, dtype: np.dtype, dim_sizes: dict[str, int]
    ) -> np.memmap:
        """Create a new tifffile file and memmap for this position."""
        from tifffile import imwrite, memmap

        _, shape = zip(*dim_sizes.items())

        # append the position key to the filename if there are multiple positions
        if (seq := self.current_sequence) and seq.sizes.get("p", 1) > 1:
            ext = ".ome.tif" if self._is_ome else ".tif"
            fname = self._filename.replace(ext, f"_{position_key}{ext}")
        else:
            fname = self._filename

        # write empty file to disk
        imwrite(
            fname,
            shape=shape,
            dtype=dtype,
            imagej=not self._is_ome,
            ome=self._is_ome,
        )

        # memory-mapped NumPy array of image data stored in TIFF file.
        mmap = memmap(fname, dtype=dtype)
        # This line is important, as tifffile.memmap appears to lose singleton dims
        mmap.shape = shape

        return mmap  # type: ignore

    def finalize_metadata(self) -> None:
        """Update TIFF files with complete OME metadata after sequence completion."""
        if not self._is_ome or not self.current_sequence:
            # Call parent to handle any base class cleanup
            super().finalize_metadata()
            return

        try:
            from pathlib import Path

            from pymmcore_plus._util import USER_DATA_MM_PATH
            from pymmcore_plus.metadata._ome import create_ome_metadata

            # Use the OME metadata path created by the engine
            ome_path = Path(USER_DATA_MM_PATH) / "ome_meta"
            sequence_path = ome_path / str(self.current_sequence.uid)

            # Check if the metadata files exist
            if not sequence_path.exists():
                warnings.warn(
                    f"OME metadata path not found: {sequence_path}", stacklevel=2
                )
                super().finalize_metadata()
                return

            # Generate rich OME metadata for the entire sequence
            ome = create_ome_metadata(sequence_path)

            # Update each TIFF file with position-specific OME metadata
            self._update_tiff_metadata_by_position(ome)

        except Exception as e:
            # Don't fail the entire acquisition if metadata update fails
            print(f"Warning: Failed to update OME metadata: {e}")

        # Call parent to handle any base class cleanup
        super().finalize_metadata()

    def _update_tiff_metadata_by_position(self, full_ome: OME) -> None:
        """Update OME-XML metadata in each TIFF file with position-specific metadata."""
        # Get all the TIFF files that were created
        for position_key in self.position_arrays:
            # Extract position index from position_key (e.g., "p0" -> 0)
            try:
                # remove 'p' prefix
                position_index = int(position_key[1:])
            except (ValueError, IndexError):
                warnings.warn(
                    f"Could not parse position index from key: {position_key}",
                    stacklevel=2,
                )
                continue

            # Find the corresponding Image in the full OME metadata
            position_image = None
            for image in full_ome.images:
                # Image IDs are in the format "Image:0", "Image:1", etc.
                if image.id == f"Image:{position_index}":
                    position_image = image
                    break

            if position_image is None:
                warnings.warn(
                    f"No OME Image found for position {position_index}", stacklevel=2
                )
                continue

            # Create a new OME object containing only this position's image
            pos_ome = OME(
                uuid=full_ome.uuid,
                images=[position_image],
                instruments=full_ome.instruments,
                plates=full_ome.plates or [],
            )

            # Reconstruct the filename for this position
            if self.current_sequence and self.current_sequence.sizes.get("p", 1) > 1:
                ext = ".ome.tif" if self._is_ome else ".tif"
                fname = self._filename.replace(ext, f"_{position_key}{ext}")
            else:
                fname = self._filename

            # Try to update the OME metadata
            self._write_ome_metadata_to_file(fname, pos_ome.to_xml())

    def _write_ome_metadata_to_file(self, fname: str, ome_xml: str) -> None:
        """Write OME metadata to a TIFF file, handling Unicode properly."""
        try:
            import tifffile
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "tifffile is required to use this handler. "
                "Please `pip install tifffile`."
            ) from e

        try:
            # NOTE: this is VERY WRONG, I'M TEMPORARILY DOING THIS TO MAKE IT WORK BUT
            # WHEN READING THE METADATA THE UNITS AFRE WRONG SO WE NEED TO FIND A FIX
            # Convert Unicode characters to ASCII-compatible alternatives
            ascii_ome_xml = ome_xml.replace("µm", "mm")
            # Ensure it's ASCII-compatible
            ascii_ome_xml.encode("ascii")

            # Write the OME-XML
            tifffile.tiffcomment(fname, ascii_ome_xml)

        except UnicodeEncodeError as e:
            warnings.warn(
                f"Failed to write OME metadata to {fname}. Unicode encoding error: {e}",
                UserWarning,
                stacklevel=2,
            )
