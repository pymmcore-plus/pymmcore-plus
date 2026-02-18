"""Handler for writing MDA sequences using the ome-writers library."""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from typing import TYPE_CHECKING

import ome_writers as omew

from ._base_runner_handler import BaseRunnerHandler, StreamSettings

if TYPE_CHECKING:
    import numpy as np
    import useq
    from typing_extensions import Self

    from pymmcore_plus.metadata import FrameMetaV1, SummaryMetaV1


def _register_cleanup_atexit(path: str) -> None:
    """Register atexit handler to cleanup directory."""

    @atexit.register
    def _cleanup(_path: str = path) -> None:  # pragma: no cover
        if os.path.isdir(_path):
            shutil.rmtree(_path, ignore_errors=True)


class OMERunnerHandler(BaseRunnerHandler):
    """MDA handler that writes to OME-ZARR or OME-TIFF using ome-writers library.

    Parameters
    ----------
    stream_settings : StreamSettings
        Settings describing the output format, path, and async/queue behavior.
    """

    def __init__(self, stream_settings: StreamSettings) -> None:
        if not stream_settings.root_path:
            raise ValueError(
                "`path` is always required unless you are using"
                "OMERunnerHandler.in_tempdir() which auto-generates a temporary"
                "directory and `path` can be empty."
            )

        self._stream_settings = stream_settings
        self._stream: omew.OMEStream | None = None

    @property
    def stream(self) -> omew.OMEStream | None:
        """The OMEStream object used for writing frames."""
        return self._stream

    @property
    def stream_settings(self) -> StreamSettings:
        """The StreamSettings used to create the stream."""
        return self._stream_settings

    @classmethod
    def in_tempdir(
        cls,
        suffix: str | None = ".ome.zarr",
        prefix: str | None = "pymmcp_runner_",
        dir: str | os.PathLike[str] | None = None,
        cleanup_atexit: bool = True,
        stream_settings: StreamSettings | None = None,
    ) -> Self:
        """Create an OMERunnerHandler that writes to a temporary directory.

        Parameters
        ----------
        suffix : str, optional
            If specified, the directory name will end with this suffix. Default is
            ".ome.zarr".
        prefix : str, optional
            If specified, the directory name will begin with this prefix. Default is
            "pymmcp_runner_".
        dir : str or PathLike, optional
            If specified, the temp directory will be created inside this directory,
            otherwise a default directory is used (tempfile.gettempdir()).
        cleanup_atexit : bool, optional
            Whether to automatically cleanup the temporary directory when the python
            process exits. Default is True.
        stream_settings : StreamSettings, optional
            Settings describing the output format. If `root_path` is set, it
            will be joined inside the temporary directory. If None (default), a
            StreamSettings with the temp directory as `root_path` and format
            "tensorstore" will be used.
        """
        temp_dir = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        # Remove the empty directory so that create_stream can create it fresh
        # (some backends refuse to write into an existing non-zarr directory).
        os.rmdir(temp_dir)
        if cleanup_atexit:
            _register_cleanup_atexit(temp_dir)

        root_path = temp_dir
        if stream_settings is None:
            settings = StreamSettings(
                root_path=root_path, format="tensorstore", overwrite=True
            )
        else:
            if stream_settings.root_path:
                root_path = os.path.join(temp_dir, stream_settings.root_path)
            settings = StreamSettings(
                root_path=root_path,
                format=stream_settings.format,
                overwrite=stream_settings.overwrite,
            )
        return cls(settings)

    def prepare(self, sequence: useq.MDASequence, meta: SummaryMetaV1 | None) -> None:
        """Prepare the settings to create the stream."""
        self._stream = None

        if meta is None:
            raise ValueError("meta is required for OMERunnerHandler")

        image_infos = meta.get("image_infos")
        if not image_infos:
            raise ValueError(
                "Metadata must contain 'image_infos' to determine image properties."
            )
        image_info = image_infos[0]
        width = image_info.get("width")
        height = image_info.get("height")
        pixel_size = image_info.get("pixel_size_um")  # optional

        if width is None or height is None:
            raise ValueError(
                "Metadata 'image_infos' must contain 'width' and 'height' keys."
            )

        dtype = self._stream_settings.dtype or image_info.get("dtype")
        if dtype is None:
            raise ValueError(
                "Data type could not be determined. Please specify `dtype` in "
                "StreamSettings or include 'dtype' in metadata 'image_infos'."
            )

        dims = self._stream_settings.dimensions
        plate = self._stream_settings.plate
        if dims is None or plate is None:
            useq_settings = omew.useq_to_acquisition_settings(
                sequence,
                image_width=width,
                image_height=height,
                pixel_size_um=pixel_size,
            )
            if dims is None:
                dims = tuple(useq_settings.get("dimensions", ()))
            if plate is None:
                plate = useq_settings.get("plate")

        acq_settings = omew.AcquisitionSettings(
            root_path=str(self._stream_settings.root_path),
            format=self._stream_settings.format,
            dtype=dtype,
            overwrite=self._stream_settings.overwrite,
            dimensions=dims,
            plate=plate,
        )
        self._stream = omew.create_stream(settings=acq_settings)

    def writeframe(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: FrameMetaV1
    ) -> None:
        """Write a single frame to the stream."""
        self._write_frame(frame, event, meta)

    def _write_frame(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: FrameMetaV1
    ) -> None:
        """Write a single frame to the underlying stream."""
        self._stream.append(frame)  # type: ignore

    def cleanup(self) -> None:
        """Close the stream when sequence finishes."""
        if self._stream is not None:
            self._stream.close()
            self._stream = None
