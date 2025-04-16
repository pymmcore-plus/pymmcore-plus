from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import warnings
from itertools import product
from os import PathLike
from typing import TYPE_CHECKING, Any, cast

import numpy as np

from pymmcore_plus.metadata.serialize import json_dumps, json_loads

from ._util import position_sizes

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Literal, TypeAlias

    import tensorstore as ts
    import useq
    from typing_extensions import Self  # py311

    from pymmcore_plus.metadata import FrameMetaV1, SummaryMetaV1

    TsDriver: TypeAlias = Literal["zarr", "zarr3", "n5", "neuroglancer_precomputed"]
    EventKey: TypeAlias = frozenset[tuple[str, int]]

# special dimension label used when _nd_storage is False
FRAME_DIM = "frame"


class TensorStoreHandler:
    """Tensorstore handler for writing MDA sequences.

    This is a performant and shape-agnostic handler for writing MDA sequences to
    chunked storages like zarr, n5, backed by tensorstore:
    <https://google.github.io/tensorstore/>

    By default, the handler will store frames in a zarr array, with a shape of
    (nframes, *frame_shape) and a chunk size of (1, *frame_shape), i.e. each frame
    is stored in a separate chunk. To customize shape or chunking, override the
    `get_full_shape`, `get_chunk_layout`, and `get_index_domain` methods (these
    may change in the future as we learn to use tensorstore better).

    Parameters
    ----------
    driver : TsDriver, optional
        The driver to use for the tensorstore, by default "zarr".  Must be one of
        "zarr", "zarr3", "n5", or "neuroglancer_precomputed".
    kvstore : str | dict | None, optional
        The key-value store to use for the tensorstore, by default "memory://".
        A dict might look like {'driver': 'file', 'path': '/path/to/dataset.zarr'}
        see <https://google.github.io/tensorstore/kvstore/index.html#json-KvStore>
        for all options. If path is provided, the kvstore will be set to file://path
    path : str | Path | None, optional
        Convenience for specifying a local filepath. If provided, overrides the
        kvstore option, to be `file://file_path`.
    delete_existing : bool, optional
        Whether to delete the existing dataset if it exists, by default False.
    spec : Mapping, optional
        A spec to use when opening the tensorstore, by default None. Values provided
        in this object will override the default values provided by the handler.
        This is a complex object that can completely define the tensorstore, see
        <https://google.github.io/tensorstore/spec.html> for more information.

    Examples
    --------
    ```python
    from pymmcore_plus import CMMCorePlus
    from pymmcore_plus.mda.handlers import TensorStoreHandler
    from useq import MDASequence

    core = CMMCorePlus.instance()
    core.loadSystemConfiguration()

    sequence = MDASequence(
        channels=["DAPI", {"config": "FITC", "exposure": 1}],
        stage_positions=[{"x": 1, "y": 1, "name": "some position"}, {"x": 0, "y": 0}],
        time_plan={"interval": 2, "loops": 3},
        z_plan={"range": 4, "step": 0.5},
        axis_order="tpcz",
    )

    writer = TensorStoreHandler(path="example_ts.zarr", delete_existing=True)
    core.mda.run(sequence, output=writer)
    ```

    """

    def __init__(
        self,
        *,
        driver: TsDriver = "zarr",
        kvstore: str | dict | None = "memory://",
        path: str | PathLike | None = None,
        delete_existing: bool = False,
        spec: Mapping | None = None,
    ) -> None:
        try:
            import tensorstore
        except ImportError as e:
            raise ImportError("Tensorstore is required to use this handler.") from e

        self._ts = tensorstore

        self.ts_driver = driver
        self.kvstore = f"file://{path}" if path is not None else kvstore
        self.delete_existing = delete_existing
        self.spec = spec

        self._current_sequence: useq.MDASequence | None = None

        # storage of individual frame metadata
        # maps position key to list of frame metadata
        self.frame_metadatas: list[tuple[useq.MDAEvent, FrameMetaV1]] = []

        self._size_increment = 300

        self._store: ts.TensorStore | None = None
        self._futures: list[ts.Future | ts.WriteFutures] = []
        self._frame_indices: dict[EventKey, int | ts.DimExpression] = {}

        # "_nd_storage" means we're greedily attempting to store the data in a
        # multi-dimensional format based on the axes of the sequence.
        # for non-deterministic experiments, this often won't work...
        # _nd_storage False means we simply store data as a 3D array of shape
        # (nframes, y, x).  `_nd_storage` is set when a new_store is created.
        self._nd_storage: bool = True
        self._frame_index: int = 0

        # the highest index seen for each axis
        self._axis_max: dict[str, int] = {}

    @property
    def store(self) -> ts.TensorStore | None:
        """The current tensorstore."""
        return self._store

    @classmethod
    def in_tmpdir(
        cls,
        suffix: str | None = "",
        prefix: str | None = "pymmcore_zarr_",
        dir: str | PathLike[str] | None = None,
        cleanup_atexit: bool = True,
        **kwargs: Any,
    ) -> Self:
        """Create TensorStoreHandler that writes to a temporary directory.

        Parameters
        ----------
        suffix : str, optional
            If suffix is specified, the file name will end with that suffix, otherwise
            there will be no suffix.
        prefix : str, optional
            If prefix is specified, the file name will begin with that prefix, otherwise
            a default prefix is used.
        dir : str or PathLike, optional
            If dir is specified, the file will be created in that directory, otherwise
            a default directory is used (tempfile.gettempdir())
        cleanup_atexit : bool, optional
            Whether to automatically cleanup the temporary directory when the python
            process exits. Default is True.
        **kwargs
            Remaining kwargs are passed to `TensorStoreHandler.__init__`
        """
        # same as zarr.storage.TempStore, but with option not to cleanup
        path = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        if cleanup_atexit:

            @atexit.register
            def _atexit_rmtree(_path: str = path) -> None:  # pragma: no cover
                if os.path.isdir(_path):
                    shutil.rmtree(_path, ignore_errors=True)

        return cls(path=path, **kwargs)

    def reset(self, sequence: useq.MDASequence) -> None:
        """Reset state to prepare for new `sequence`."""
        self._frame_index = 0
        self._store = None
        self._futures.clear()
        self.frame_metadatas.clear()
        self._current_sequence = sequence

    @property
    def current_sequence(self) -> useq.MDASequence | None:
        """Return current sequence, or none.

        Use `.reset()` to initialize the handler for a new sequence.
        """
        return self._current_sequence

    def sequenceStarted(self, seq: useq.MDASequence, meta: SummaryMetaV1) -> None:
        """On sequence started, simply store the sequence."""
        self.reset(seq)

    def sequenceFinished(self, seq: useq.MDASequence) -> None:
        """On sequence finished, clear the current sequence."""
        if self._store is None:
            return  # pragma: no cover

        while self._futures:
            self._futures.pop().result()
        if not self._nd_storage:
            self._store = self._store.resize(
                exclusive_max=(self._frame_index, *self._store.shape[-2:])
            ).result()
        if self.frame_metadatas:
            self.finalize_metadata()

    def frameReady(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: FrameMetaV1, /
    ) -> None:
        """Write frame to the zarr array for the appropriate position."""
        if self._store is None:
            self._store = self.new_store(frame, event.sequence, meta).result()

        ts_index: ts.DimExpression | int
        if self._nd_storage:
            ts_index = self._event_index_to_store_index(event.index)
        else:
            if self._frame_index >= self._store.shape[0]:
                self._store = self._expand_store(self._store).result()
            ts_index = self._frame_index
            # store reverse lookup of event.index -> frame_index
            self._frame_indices[frozenset(event.index.items())] = ts_index

        # write the new frame asynchronously
        self._futures.append(self._store[ts_index].write(frame))

        # store, but do not process yet, the frame metadata
        self.frame_metadatas.append((event, meta))
        # update the frame counter
        self._frame_index += 1
        # remember the highest index seen for each axis
        for k, v in event.index.items():
            self._axis_max[k] = max(self._axis_max.get(k, 0), v)

    def isel(
        self,
        indexers: Mapping[str, int | slice] | None = None,
        **indexers_kwargs: int | slice,
    ) -> np.ndarray:
        """Select data from the array."""
        # FIXME: will fail on slices
        indexers = {**(indexers or {}), **indexers_kwargs}
        ts_index = self._event_index_to_store_index(indexers)
        if self._store is None:  # pragma: no cover
            warnings.warn("No data written.", stacklevel=2)
            return np.empty([])
        return self._store[ts_index].read().result().squeeze()  # type: ignore [no-any-return]

    def new_store(
        self, frame: np.ndarray, seq: useq.MDASequence | None, meta: FrameMetaV1
    ) -> ts.Future[ts.TensorStore]:
        shape, chunks, labels = self.get_shape_chunks_labels(frame.shape, seq)
        self._nd_storage = FRAME_DIM not in labels
        return self._ts.open(
            self.get_spec(),
            create=True,
            delete_existing=self.delete_existing,
            dtype=self._ts.dtype(frame.dtype),
            shape=shape,
            chunk_layout=self._ts.ChunkLayout(chunk_shape=chunks),
            domain=self._ts.IndexDomain(labels=labels),
        )

    def get_shape_chunks_labels(
        self, frame_shape: tuple[int, ...], seq: useq.MDASequence | None
    ) -> tuple[tuple[int, ...], tuple[int, ...], tuple[str, ...]]:
        labels: tuple[str, ...]
        if seq is not None and seq.sizes:
            # expand the sizes to include the largest size we encounter for each axis
            # in the case of positions with subsequences, we'll still end up with a
            # jagged array, but it won't take extra space, and we won't get index errors
            max_sizes = dict(seq.sizes)
            for psize in position_sizes(seq):
                for k, v in psize.items():
                    max_sizes[k] = max(max_sizes.get(k, 0), v)

            # remove axes with length 0
            labels, sizes = zip(*(x for x in max_sizes.items() if x[1]))
            full_shape: tuple[int, ...] = (*sizes, *frame_shape)
        else:
            labels = (FRAME_DIM,)
            full_shape = (self._size_increment, *frame_shape)

        chunks = [1] * len(full_shape)
        chunks[-len(frame_shape) :] = frame_shape
        labels = (*labels, "y", "x")
        return full_shape, tuple(chunks), labels

    def get_spec(self) -> dict:
        """Construct the tensorstore spec."""
        spec = {"driver": self.ts_driver, "kvstore": self.kvstore}
        if self.spec:
            _merge_nested_dicts(spec, self.spec)

        # HACK
        if self.ts_driver == "zarr":
            meta = cast("dict", spec.setdefault("metadata", {}))
            if "dimension_separator" not in meta:
                meta["dimension_separator"] = "/"
        return spec

    def finalize_metadata(self) -> None:
        """Finalize and flush metadata to storage."""
        if not (store := self._store) or not store.kvstore:
            return  # pragma: no cover

        metadata = {"frame_metadatas": [m[1] for m in self.frame_metadatas]}
        if not self._nd_storage:
            metadata["frame_indices"] = [
                (tuple(dict(k).items()), v)  # type: ignore
                for k, v in self._frame_indices.items()
            ]

        if self.ts_driver.startswith("zarr"):
            store.kvstore.write(
                ".zattrs", json_dumps(metadata).decode("utf-8")
            ).result()
        elif self.ts_driver == "n5":  # pragma: no cover
            attrs = json_loads(store.kvstore.read("attributes.json").result().value)
            attrs.update(metadata)
            store.kvstore.write("attributes.json", json_dumps(attrs).decode("utf-8"))

    def _expand_store(self, store: ts.TensorStore) -> ts.Future[ts.TensorStore]:
        """Grow the store by `self._size_increment` frames.

        This is used when _nd_storage mode is False and we've run out of space.
        """
        new_shape = [self._frame_index + self._size_increment, *store.shape[-2:]]
        return store.resize(exclusive_max=new_shape, expand_only=True)

    def _event_index_to_store_index(
        self, index: Mapping[str, int | slice]
    ) -> ts.DimExpression:
        """Convert event index to store index.

        The return value is safe to use as an index to self._store[...]
        """
        if self._nd_storage:
            keys, values = zip(*index.items())
            return self._ts.d[keys][values]

        if any(isinstance(v, slice) for v in index.values()):
            idx: list | int | ts.DimExpression = self._get_frame_indices(index)
        else:
            try:
                idx = self._frame_indices[frozenset(index.items())]  # type: ignore
            except KeyError as e:
                raise KeyError(f"Index {index} not found in frame_indices.") from e
        return self._ts.d[FRAME_DIM][idx]

    def _get_frame_indices(self, indexers: Mapping[str, int | slice]) -> list[int]:
        """Convert indexers (with slices) to a list of frame indices."""
        # converting slice objects to actual indices
        axis_indices: dict[str, Sequence[int]] = {}
        for k, v in indexers.items():
            if isinstance(v, slice):
                axis_indices[k] = tuple(range(*v.indices(self._axis_max.get(k, 0) + 1)))
            else:
                axis_indices[k] = (v,)

        indices: list[int] = []
        for p in product(*axis_indices.values()):
            key = frozenset(dict(zip(axis_indices.keys(), p)).items())
            try:
                indices.append(self._frame_indices[key])
            except KeyError:  # pragma: no cover
                warnings.warn(
                    f"Index {dict(key)} not found in frame_indices.", stacklevel=2
                )
        return indices


def _merge_nested_dicts(dict1: dict, dict2: Mapping) -> None:
    """Merge two nested dictionaries.

    Values in dict2 will override values in dict1.
    """
    for key, value in dict2.items():
        if key in dict1 and isinstance(dict1[key], dict) and isinstance(value, dict):
            _merge_nested_dicts(dict1[key], value)
        else:
            dict1[key] = value
