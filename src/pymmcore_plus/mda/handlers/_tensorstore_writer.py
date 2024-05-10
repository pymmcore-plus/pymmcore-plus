from __future__ import annotations

import json
from typing import TYPE_CHECKING, Mapping

import tensorstore as ts

if TYPE_CHECKING:
    import numpy as np
    import useq


class TensorStoreWriter:
    def __init__(self, path: str | None = None, overwrite: bool = False) -> None:
        # storage of individual frame metadata
        # maps position key to list of frame metadata
        self.frame_metadatas: list[tuple[useq.MDAEvent, dict]] = []
        self.resize_at = 100
        self.delete_existing = overwrite
        self.driver = "file" if path else "memory"
        self.path = path or ""
        self.compressor = None
        self._store: ts.TensorStore | None = None
        self._counter = 0
        self._futures: list[ts.Future] = []
        self._indices: dict[frozenset[tuple[str, int]], int] = {}

    def sequenceStarted(self, seq: useq.MDASequence) -> None:
        """On sequence started, simply store the sequence."""
        self._counter = 0
        self._store = None
        self.frame_metadatas.clear()
        self.current_sequence = seq

    def sequenceFinished(self, seq: useq.MDASequence) -> None:
        """On sequence finished, clear the current sequence."""
        if self._store is None:
            return
        self._futures.append(
            self._store.resize(exclusive_max=(self._counter, *self._store.shape[-2:]))
        )
        for f in self._futures:
            f.result()
        if self.frame_metadatas:
            data = []
            for event, meta in self.frame_metadatas:
                js = event.model_dump_json(exclude={"sequence"}, exclude_defaults=True)
                meta["Event"] = json.loads(js)
                data.append(meta)
            self._store.kvstore.write(".zattrs", json.dumps({"frame_metadatas": data}))

    def frameReady(self, frame: np.ndarray, event: useq.MDAEvent, meta: dict) -> None:
        """Write frame to the zarr array for the appropriate position."""
        if self._store is None:
            self._store = self._make_tensorstore(self._make_spec(frame))
        elif self._counter >= self._store.shape[0]:
            self._store = self._store.resize(
                exclusive_max=(self._counter + self.resize_at, *self._store.shape[-2:])
            ).result()

        self._indices[frozenset(event.index.items())] = self._counter
        self._futures.append(self._store[self._counter].write(frame))
        self.frame_metadatas.append((event, meta))
        self._counter += 1

    def isel(
        self,
        indexers: Mapping[str, int | slice] | None = None,
        **indexers_kwargs: int | slice,
    ) -> np.ndarray:
        """Select data from the array."""
        # FIXME: will fail on slices
        index = self._indices[frozenset(indexers.items())]
        return self._store[index].read().result()

    def _make_spec(self, frame: np.ndarray) -> dict:
        return {
            "kvstore": {"driver": self.driver, "path": self.path},
            "create": True,
            "delete_existing": self.delete_existing,
            "driver": "zarr",
            "metadata": {
                "zarr_format": 2,
                "shape": [self.resize_at, *frame.shape],
                "chunks": [1, *frame.shape],
                "dtype": frame.dtype.str,
                # "compressor": self.compressor,
                "fill_value": 0,
                "order": "C",
            },
        }

    def _make_tensorstore(self, spec: dict) -> ts.TensorStore:
        return ts.open(spec).result()
