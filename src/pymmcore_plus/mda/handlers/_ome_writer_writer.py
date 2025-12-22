from __future__ import annotations

import atexit
import contextlib
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from ome_writers import create_stream, dims_from_useq

from pymmcore_plus.metadata._ome import _get_dimension_info, create_ome_metadata

if TYPE_CHECKING:
    from datetime import timedelta

    import numpy as np
    import useq
    from ome_writers import BackendName

    from pymmcore_plus.metadata.schema import FrameMetaV1, SummaryMetaV1


class OMEWriterHandler:
    """A handler to write images and metadata to OME-Zarr or OME-TIFF format.

    Parameters
    ----------
    path : str
        Path to the output file or directory.
    backend : Literal["acquire-zarr", "tensorstore", "tiff", "auto"], optional
        The backend to use for writing the data. Options are:

        - "acquire-zarr": Use acquire-zarr backend.
        - "tensorstore": Use tensorstore backend.
        - "tiff": Use tifffile backend.
        - "auto": Automatically determine the backend based on the file extension.

        Default is "auto".
    overwrite : bool, optional
        Whether to overwrite existing files or directories. Default is False.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        backend: Literal[BackendName, "auto"] = "auto",
        overwrite: bool = False,
    ) -> None:
        if path is None:
            path = self._tmp_dir()

        self.path = path
        self.backend: Literal[BackendName, "auto"] = backend
        self.overwrite = overwrite

        self._summary_metadata: SummaryMetaV1 | None = None
        self._frame_metadatas: list[FrameMetaV1] = []

    def sequenceStarted(self, seq: useq.MDASequence, meta: SummaryMetaV1) -> None:
        """On sequence started, initialize the OME writer stream."""
        self._summary_metadata = meta
        self._frame_metadatas.clear()

        z_step = abs(getattr(seq.z_plan, "step", 1.0))
        if interval := getattr(seq.time_plan, "interval", None):
            t_step = cast("timedelta", interval).total_seconds()
        else:
            t_step = 1.0

        dim_info = _get_dimension_info(meta["image_infos"])
        self.stream = create_stream(
            self.path,
            dtype=dim_info.dtype,
            dimensions=dims_from_useq(
                seq,
                image_width=dim_info.width,
                image_height=dim_info.height,
                units={
                    "t": (t_step, "s"),
                    "z": (z_step, "um"),
                    "y": (dim_info.pixel_size_um, "um"),
                    "x": (dim_info.pixel_size_um, "um"),
                },
            ),
            backend=self.backend,
            overwrite=self.overwrite,
        )

    def frameReady(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: FrameMetaV1
    ) -> None:
        """On each frame ready, append the frame to the OME writer stream."""
        self.stream.append(frame)
        self._frame_metadatas.append(meta)

    def sequenceFinished(self, seq: useq.MDASequence) -> None:
        """On sequence finished, write the OME metadata."""
        if self._summary_metadata is None:
            return

        ome_meta = create_ome_metadata(self._summary_metadata, self._frame_metadatas)
        # TODO: (TEMPORARY)
        # need an api to write the OME metadata to the OMEWriter stream
        # working for both ngff-zarr and ome-tiff
        out = Path(self.path, "meta.json")
        out.write_text(ome_meta.model_dump_json(indent=2, exclude_unset=True))

    @staticmethod
    def _tmp_dir() -> str:
        """Create a temporary directory for storing OME files.

        Used when no path is provided
        """
        path = tempfile.mkdtemp(suffix=".ome.zarr", prefix="pymmcore_zarr_")

        @atexit.register
        def _cleanup_temp_dir() -> None:
            with contextlib.suppress(Exception):
                shutil.rmtree(path)

        return path
