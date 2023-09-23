"""Simple TIFF writer for MDASequences."""

from __future__ import annotations

import json
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Mapping, Sequence

if TYPE_CHECKING:
    import numpy as np
    import useq

FRAME_KEY = "frame"


class TiffSeriesWriter:
    """Write each frame of an MDA to a directory as individual TIFF files.

    This writer It assumes very little about the sequence, and simply writes each frame
    to a TIFF file in the specified directory. It is a good option for ragged or sparse
    sequences, or where the exact number of frames is not known in advance.

    The metadata for each frame is stored in a JSON file in the directory (by default,
    named ".frame_metadata.json").  The metadata is stored as a dict, with the key
    being the index string for the frame (see index_template), and the value being
    the metadata dict for that frame.

    The metadata for the entire MDA sequence is stored in a JSON file in the directory
    (by default, named ".sequence_metadata.json").

    !!! note

        This writer outputs a format that is easily consumed by `tifffile.imread`
        using the `pattern="axes"` option.

        ```python
        from tifffile import imread
        data = imread("my_folder/*.tif", pattern="axes")

        # or with zarr
        import zarr
        store = imread('data_folder/*.tif', pattern='axes', aszarr=True)
        data = zarr.open(store)
        ```

    Parameters
    ----------
    directory: Path | str
        The directory to write the TIFF files to.
    prefix: str
        A prefix to add to the TIFF file names.
    overwrite: bool
        Whether to overwrite the directory if it already exists.  If False, a
        FileExistsError will be raised if the directory already exists.
    imwrite_kwargs: dict | None
        Extra keyword arguments to pass to tifffile.imwrite.
    """

    FRAME_META_PATH: ClassVar[str] = ".frame_metadata.json"
    SEQ_META_PATH: ClassVar[str] = ".sequence_metadata.json"

    def __init__(
        self,
        directory: Path | str,
        prefix: str = "",
        *,
        overwrite: bool = False,
        include_frame_count: bool = True,
        imwrite_kwargs: dict | None = None,
    ) -> None:
        try:
            from tifffile import imwrite

        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "tifffile is required to use this handler. "
                "Please `pip install tifffile`."
            ) from e

        self._imwrite = imwrite
        self._imwrite_kwargs = imwrite_kwargs or {}

        self._directory = Path(directory).expanduser().resolve()
        if self._directory.exists():
            if not overwrite:
                raise FileExistsError(
                    f"Directory {self._directory} already exists. "
                    "Set `overwrite=True` to overwrite."
                )
            import shutil

            shutil.rmtree(self._directory)

        self._prefix = prefix

        # ongoing dict of frame meta... stored for easy rewrite without reading
        self._frame_metadata: dict[str, dict] = {}
        self._frame_meta_file = self._directory.joinpath(self.FRAME_META_PATH)
        self._seq_meta_file = self._directory.joinpath(self.SEQ_META_PATH)

        # options related to file naming
        # FIXME:
        # the fixed {index_value:03} is too generous for some indices (channel)
        # and too small for others (time)
        # need to find a way to make this more flexible
        # until then, we don't expose these as a parameter
        self._delimiter = "_"
        self._include_frame_count = include_frame_count
        self._counter = count()
        self._ext = ".tif"

        self._name_template = ""  # generated in sequenceStarted

    def sequenceStarted(self, seq: useq.MDASequence) -> None:
        """Store the sequence metadata and reset the frame counter."""
        self._counter = count()  # reset counter
        self._directory.mkdir(parents=True, exist_ok=True)

        self._current_sequence = seq
        if seq:
            self._name_template = self.fname_template(
                seq.used_axes,
                prefix=self._prefix,
                extension=self._ext,
                delimiter=self._delimiter,
                include_frame_count=self._include_frame_count,
            )
            # make directory and write metadata
            self._seq_meta_file.write_text(seq.json(exclude_unset=True, indent=4))

    def frameReady(self, frame: np.ndarray, event: useq.MDAEvent, meta: dict) -> None:
        """Write a frame to disk."""
        # WRITE DATA TO DISK
        frame_idx = next(self._counter)
        if self._name_template:
            if FRAME_KEY in self._name_template:
                indices: Mapping = {**event.index, FRAME_KEY: frame_idx}
            else:
                indices = event.index
            name = self._name_template.format(**indices)
        else:
            # if we don't have a sequence, just use the counter
            name = f"{self._prefix}_fr{frame_idx:05}.tif"
        self._imwrite(self._directory / name, frame, **self._imwrite_kwargs)

        # write metadata to disk
        meta["Event"] = json.loads(event.json(exclude={"sequence"}, exclude_unset=True))
        self._frame_metadata[name] = meta
        self._frame_meta_file.write_text(json.dumps(self._frame_metadata, indent=2))

    @staticmethod
    def fname_template(
        axes: Mapping[str, int] | Sequence[str],
        prefix: str = "",
        extension: str = ".tif",
        delimiter: str = "_",
        include_frame_count: bool = True,
    ) -> str:
        """Generate a string template for file names.

        Parameters
        ----------
        axes : Mapping[str, int] | Sequence[str]
            The axes to include in the template. If a mapping, the values are the
            number of digits to use for each axis. If a sequence, the number of digits
            is determined automatically.
        prefix : str, optional
            A prefix to add to the template, by default ""
        extension : str, optional
            The file extension to use, by default ".tif"
        delimiter : str, optional
            The delimiter to use between items in the template, by default "_"
        include_frame_count : bool, optional
            Whether to include a frame count item in the template (`{frame:05}`). This
            will come after the prefix and before the indices. It is a good way to
            ensure unique keys. by default True

        Examples
        --------
        >>> SimpleTiffWriter.fname_template("tcz")
        '{frame:05}_t{t:04}_c{c:02}_z{z:03}.tif'
        >>> fname_template({"c": 2, "z": 3}, "some_prefix")
        'some_prefix{frame:05}_c{c:02}_z{z:03}.tif'
        """
        # determine the number of digits to use for each axis
        # if an axis is not in ndigits, it will use 3 digits
        ndigits = {"t": 4, "c": 2}  # Too magic?
        if isinstance(axes, Mapping):
            ndigits = {**ndigits, **axes}
        ax_lengths = {ax: ndigits.get(ax.lower(), 3) for ax in axes}

        items = delimiter.join(
            (f"{ax}{{{ax}:0{lngth}}}" for ax, lngth in ax_lengths.items())
        )
        if prefix and not prefix.endswith(delimiter):
            prefix += delimiter
        if include_frame_count:
            prefix = prefix.rstrip(delimiter)
            if prefix:
                prefix += "-"
            prefix += f"{{{FRAME_KEY}:05}}{delimiter}"
        return f"{prefix}{items}{extension}"
