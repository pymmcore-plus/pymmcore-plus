from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ome_writers import create_stream, dims_from_useq

if TYPE_CHECKING:
    import os

    import numpy as np
    import useq

    from pymmcore_plus.metadata.schema import FrameMetaV1, SummaryMetaV1


class OMEZarrWriter:
    def __init__(
        self,
        store: str | os.PathLike | None = None,
        *,
        overwrite: bool = False,
    ) -> None:
        if store is None:
            store = tempfile.mkdtemp(suffix=".ome.zarr", prefix="pymmcore_zarr_")
        self._store = store
        self._summary_metadata: SummaryMetaV1 | None = None
        self._frame_metadatas: list[FrameMetaV1] = []
        self._overwrite = overwrite

    def frameReady(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: FrameMetaV1
    ) -> None:
        self.stream.append(frame)
        self._frame_metadatas.append(meta)

    def sequenceStarted(self, seq: useq.MDASequence, meta: SummaryMetaV1) -> None:
        from pymmcore_plus.metadata._ome import _get_dimension_info

        self._summary_metadata = meta
        dim_info = _get_dimension_info(meta["image_infos"])
        dimensions = dims_from_useq(
            seq,
            image_width=dim_info.width,
            image_height=dim_info.height,
        )
        self.stream = create_stream(
            self._store,
            dtype=dim_info.dtype,
            dimensions=dimensions,
            backend="tensorstore",
            overwrite=self._overwrite,
        )

    def sequenceFinished(self, seq: useq.MDASequence) -> None:
        """On sequence finished, clear the current sequence."""
        from pymmcore_plus.metadata._ome import create_ome_metadata

        ome_meta = create_ome_metadata(self._summary_metadata, self._frame_metadatas)
        Path(self._store, "meta.json").write_text(
            ome_meta.model_dump_json(indent=2, exclude_unset=True)
        )
