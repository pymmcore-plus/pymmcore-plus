"""Simple Image sequence writer for MDASequences.

Writes each frame of an MDA to a directory as individual TIFF files by default,
but can write to other formats if `imageio` is installed or a custom writer is
provided.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, ClassVar, cast

from pymmcore_plus.metadata.serialize import json_dumps

from ._util import get_full_sequence_axes

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt
    import useq
    from typing_extensions import TypeAlias  # py310

    from pymmcore_plus.metadata.schema import FrameMetaV1

    ImgWriter: TypeAlias = Callable[[str, npt.NDArray], Any]

FRAME_KEY = "frame"


class ImageSequenceWriter:
    """Write each frame of an MDA to a directory as individual image files.

    This writer assumes very little about the sequence, and simply writes each frame
    to a file in the specified directory. It is a good option for ragged or sparse
    sequences, or where the exact number of frames is not known in advance.

    The default output format is TIFF, backed by `tifffile.imwrite`, but many other
    common extensions can be used if `imageio` is installed. Or, you can pass a
    custom writer function to the `imwrite` argument.

    The metadata for each frame is stored in a JSON file in the directory (by default,
    named "_frame_metadata.json").  The metadata is stored as a dict, with the key
    being the index string for the frame (see index_template), and the value being
    the metadata dict for that frame.

    The metadata for the entire MDA sequence is stored in a JSON file in the directory
    (by default, named "_useq_MDASequence.json").

    !!! note

        This writer outputs a format that is easily consumed by `tifffile.imread`
        using the `pattern="axes"` option.

        ```python
        from tifffile import imread

        data = imread("my_folder/*.tif", pattern="axes")

        # or with zarr
        import zarr

        store = imread("data_folder/*.tif", pattern="axes", aszarr=True)
        data = zarr.open(store)
        ```

    Parameters
    ----------
    directory: Path | str
        The directory to write the files to.
    extension: str
        The file extension to use.  By default, ".tif".
    prefix: str
        A prefix to add to the file names.  By default, no prefix is added.
    imwrite: Callable[[str, npt.NDArray], Any] | None
        A function to write the image data to disk. The function should take a filename
        and image data as positional arguments. If None, a writer will be selected based
        on the extension. For the default extension `.tif`, this will be
        `tifffile.imwrite` (which must be installed).
    overwrite: bool
        Whether to overwrite the directory if it already exists.  If False, a
        FileExistsError will be raised if the directory already exists.
    include_frame_count: bool
        Whether to include a frame count item in the template (`{frame:05}`). This
        will come after the prefix and before the indices. It is a good way to
        ensure unique keys. by default True
    imwrite_kwargs: dict | None
        Extra keyword arguments to pass to the `imwrite` function.
    """

    FRAME_META_PATH: ClassVar[str] = "_frame_metadata.json"
    SEQ_META_PATH: ClassVar[str] = "_useq_MDASequence.json"

    def __init__(
        self,
        directory: Path | str,
        extension: str = ".tif",
        prefix: str = "",
        *,
        imwrite: ImgWriter | None = None,
        overwrite: bool = False,
        include_frame_count: bool = True,
        imwrite_kwargs: dict | None = None,
    ) -> None:
        self._imwrite = self._pick_writer(imwrite, extension)
        self._imwrite_kwargs = imwrite_kwargs or {}
        self._prefix = prefix
        self._ext = extension

        self._directory = Path(directory).expanduser().resolve()
        if self._directory.exists():
            if not overwrite:
                raise FileExistsError(
                    f"Directory {self._directory} already exists. "
                    "Set `overwrite=True` to overwrite."
                )
            import shutil

            shutil.rmtree(self._directory)

        # ongoing dict of frame meta... stored for easy rewrite without reading
        self._frame_metadata: dict[str, FrameMetaV1] = {}
        self._frame_meta_file = self._directory.joinpath(self.FRAME_META_PATH)
        self._seq_meta_file = self._directory.joinpath(self.SEQ_META_PATH)

        # options related to file naming
        self._delimiter = "_"
        self._counter = count()
        self._include_frame_count = include_frame_count
        self._name_template = ""  # generated in sequenceStarted

    def _pick_writer(
        self, imwrite: ImgWriter | None, ext: str
    ) -> Callable[[str, npt.NDArray], Any]:
        if imwrite:
            if not callable(imwrite):
                raise TypeError("imwrite argument must be callable or None")
            return imwrite

        msg = (
            "{0!r} is required to write {1} files. "
            "Please `pip install {0}` or pass an imwrite callable."
        )

        if ext in {".tif", ".tiff"}:
            try:
                import tifffile
            except ImportError as e:  # pragma: no cover
                raise ImportError(msg.format("tifffile", ext)) from e
            return cast("ImgWriter", tifffile.imwrite)

        elif ext in IIO_FORMATS:
            try:
                import imageio
            except ImportError as e:  # pragma: no cover
                raise ImportError(msg.format("imageio", ext)) from e
            return cast("ImgWriter", imageio.imwrite)

        raise ValueError(
            f"Unable to find a writer for extension {ext}. "
            "You may pass a writer explicitly with the `imwrite=` argument."
        )

    def sequenceStarted(self, seq: useq.MDASequence) -> None:
        """Store the sequence metadata and reset the frame counter."""
        self._counter = count()  # reset counter
        self._frame_metadata = {}  # reset metadata
        self._directory.mkdir(parents=True, exist_ok=True)

        self._current_sequence = seq
        axes = get_full_sequence_axes(seq)
        self._first_index = dict.fromkeys(axes, 0)
        if seq:
            self._name_template = self.fname_template(
                axes,
                prefix=self._prefix,
                extension=self._ext,
                delimiter=self._delimiter,
                include_frame_count=self._include_frame_count,
            )
            # make directory and write metadata
            self._seq_meta_file.write_text(
                seq.model_dump_json(exclude_unset=True, indent=2)
            )

    def sequenceFinished(self, seq: useq.MDASequence) -> None:
        # write final frame metadata to disk
        self._frame_meta_file.write_bytes(json_dumps(self._frame_metadata, indent=2))

    def frameReady(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: FrameMetaV1, /
    ) -> None:
        """Write a frame to disk."""
        frame_idx = next(self._counter)
        if self._name_template:
            if FRAME_KEY in self._name_template:
                indices = {**self._first_index, **event.index, FRAME_KEY: frame_idx}
            else:
                indices = {**self._first_index, **event.index}
            filename = self._name_template.format(**indices)
        else:
            # if we don't have a sequence, just use the counter
            filename = f"{self._prefix}_fr{frame_idx:05}.tif"

        # WRITE DATA TO DISK
        self._imwrite(str(self._directory / filename), frame, **self._imwrite_kwargs)

        # store metadata
        self._frame_metadata[filename] = meta
        # write metadata to disk every 10 frames
        if frame_idx % 10 == 0:
            self._frame_meta_file.write_bytes(
                json_dumps(self._frame_metadata, indent=2)
            )

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

        lower_axes = (ax.lower() for ax in axes)
        ax_lengths = {ax: ndigits.get(ax, 3) for ax in lower_axes}

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


# fmt: off
IIO_FORMATS = {
    '.lfp', '.hdp', '.tif', '.hdr', '.wdp', '.fz', '.nhdr', '.ppm', '.pict', '.bmq',
    '.cut', '.gipl', '.pfm', '.ico', '.jpg', '.lfr', '.orf', '.nef', '.dc2', '.jfif',
    '.fli', '.pef', '.img.gz', '.rw2', '.grib', '.wmf', '.kdc', '.jif', '.arw', '.img',
    '.jpf', '.jpx', '.cs1', '.raf', '.fit', '.sr2', '.wbmp', '.dcm', '.dds', '.gdcm',
    '.iff', '.crw', '.mri', '.mpo', '.erf', '.jng', '.pcx', '.rgba', '.npz', '.pct',
    '.vtk', '.iiq', '.sgi', '.gbr', '.3fr', '.jpeg', '.kc2', '.nrw', '.dicom', '.tga',
    '.mnc', '.nii.gz', '.cur', '.pxn', '.psd', '.k25', '.webp', '.mdc', '.cine', '.swf',
    '.cap', '.ps', '.lsm', '.bsdf', '.g3', '.fpx', '.dsc', '.pbm', '.wbm', '.jxr',
    '.sti', '.dcx', '.mrw', '.nia', '.hdf5', '.pxr', '.gif', '.pic', '.ptx', '.pcd',
    '.bay', '.mnc2', '.iim', '.fts', '.fff', '.cr2', '.rwl', '.mhd', '.bufr', '.eps',
    '.flc', '.jpc', '.lbm', '.xbm', '.hdf', '.rwz', '.j2k', '.jpe', '.mic', '.dcr',
    '.ecw', '.msp', '.raw', '.drf', '.dng', '.mef', '.qtk', '.jp2', '.srw', '.h5',
    '.pgm', '.emf', '.wap', '.koa', '.bw', '.targa', '.png', '.ftu', '.stk', '.srf',
    '.j2c', '.exr', '.ct', '.tiff', '.nrrd', '.mgh', '.mos', '.mha', '.ipl', '.rdc',
    '.ftc', '.xpm', '.rgb', '.ia', '.im', '.ras', '.nii', '.fits', '.icns', '.bmp'
}
# fmt: on
