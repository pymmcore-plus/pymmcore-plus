"""Handler for writing MDA sequences using the ome-writers library."""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import ome_writers as omew

if TYPE_CHECKING:
    import numpy as np
    import useq
    from ome_writers._schema import DimensionList, DTypeStr
    from typing_extensions import Self

    from pymmcore_plus.metadata import FrameMetaV1, SummaryMetaV1


class StreamSettings(omew.AcquisitionSettings):
    """Acquisition settings for MDA output.

    Subclass of `ome_writers.AcquisitionSettings` with `dimensions`, `dtype`,
    and `plate` made optional, since they can be derived from the MDASequence
    and metadata at runtime.
    """

    dimensions: DimensionList | None = None
    dtype: DTypeStr | None = None
    plate: omew.Plate | None = None

    def _validate_storage_order(self) -> StreamSettings:
        if self.dimensions is None:
            return self
        return super()._validate_storage_order()  # type: ignore[no-any-return]

    def _validate_plate_positions(self) -> StreamSettings:
        if self.dimensions is None:
            return self
        return super()._validate_plate_positions()  # type: ignore[no-any-return]


def _register_cleanup_atexit(path: str) -> None:
    """Register atexit handler to cleanup directory."""

    @atexit.register
    def _cleanup(_path: str = path) -> None:  # pragma: no cover
        if os.path.isdir(_path):
            shutil.rmtree(_path, ignore_errors=True)


class OMERunnerHandler:
    """MDA handler that writes to OME-ZARR or OME-TIFF using ome-writers library."""

    def __init__(self, stream_settings: StreamSettings) -> None:
        if not stream_settings.root_path:
            raise ValueError(
                "`path` is required. Use OMERunnerHandler.in_tempdir() for temporary "
                "directory."
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
    def in_tempdir(cls, stream_settings: StreamSettings) -> Self:
        """Create an OMERunnerHandler with a temporary directory as the stream path."""
        temp_dir = tempfile.mkdtemp(prefix="pymmcore_plus_ome_runner_")
        _register_cleanup_atexit(temp_dir)
        stream_settings = StreamSettings(
            root_path=str(Path(temp_dir) / (stream_settings.root_path or "_pymmcp")),
            format=stream_settings.format,
            overwrite=stream_settings.overwrite,
        )
        return cls(stream_settings)

    def prepare(self, sequence: useq.MDASequence, meta: SummaryMetaV1 | None) -> None:
        """Prepare the settings to create the stream."""
        if meta is None:
            raise ValueError("meta is required for OMERunnerHandler")
        self._stream = None

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
        """Write frame to the stream."""
        if self._stream is not None:
            self._stream.append(frame)
        else:
            raise RuntimeError("Stream is not initialized. Call `prepare()` first.")

    def cleanup(self) -> None:
        """Close the stream when sequence finishes."""
        if self._stream is not None:
            self._stream.close()
            self._stream = None
