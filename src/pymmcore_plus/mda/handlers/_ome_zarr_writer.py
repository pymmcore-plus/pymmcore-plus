from __future__ import annotations

import atexit
import json
import os.path
import shutil
import tempfile
from typing import TYPE_CHECKING, Any, Literal, MutableMapping, Protocol

if TYPE_CHECKING:
    from os import PathLike
    from typing import ContextManager, Sequence

    import numpy as np
    import useq
    import zarr
    from fsspec import FSMap
    from numcodecs.abc import Codec
    from typing_extensions import TypedDict

    class ZarrSynchronizer(Protocol):
        def __getitem__(self, key: str) -> ContextManager:
            ...

    class ArrayCreationKwargs(TypedDict, total=False):
        compressor: str | Codec
        fill_value: int | None
        order: Literal["C", "F"]
        synchronizer: ZarrSynchronizer | None
        overwrite: bool
        filters: Sequence[Codec] | None
        cache_attrs: bool
        read_only: bool
        object_codec: Codec | None
        dimension_separator: Literal["/", "."] | None
        write_empty_chunks: bool


POS_PREFIX = "p"


class OMEZarrWriter:
    """MDA handler that writes to a zarr file following the ome-ngff spec.

    This implements v0.4
    https://ngff.openmicroscopy.org/0.4/index.html

    It also aims to be compatible with the xarray Zarr spec:
    https://docs.xarray.dev/en/latest/internals/zarr-encoding-spec.html

    Note: this does *not* currently calculate any additional pyramid levels.
    But it would be easy to do so after acquisition.
    Chunk size is currently 1 XY plane.

    Zarr directory structure will be:

    ```
    root.zarr/
    ├── .zgroup                 # group metadata
    ├── .zattrs                 # contains ome-multiscales metadata
    │
    ├── p0                      # each position is a separate <=5D array
    │   ├── .zarray
    │   ├── .zattrs
    │   └── t                   # nested directories for each dimension
    │       └── c               # (only collected dimensions will be present)
    │           └── z
    │               └── y
    │                   └── x   # chunks will be each XY plane
    ├── ...
    ├── pn
    │   ├── .zarray
    │   ├── .zattrs
    │   └── t...
    ```

    Parameters
    ----------
    store: MutableMapping | str | None
        Zarr store or path to directory in file system to write to.
        Semantics are the same as for `zarr.group`: If a string, it is interpreted as a
        path to a directory. If None, an in-memory store is used.  May also be any
        mutable mapping or instance of `zarr.storage.BaseStore`.
    overwrite : bool
        If True, delete any pre-existing data in `store` at `path` before
        creating the group. If False, raise an error if there is already data
        in `store` at `path`. by default False.
    synchronizer : ZarrSynchronizer | None, optional
        Array synchronizer passed to `zarr.group`.
    zarr_version : {2, 3, None}, optional
        Zarr version passed to `zarr.group`.
    array_kwargs : dict, optional
        Keyword arguments passed to `zarr.group.create` when creating the arrays.
        This may be used to set the zarr `compressor`, `fill_value`, `synchronizer`,
        etc... Default is `{'dimension_separator': '/'}`.
    minify_attrs_metadata : bool, optional
        If True, zattrs metadata will be read from disk, minified, and written
        back to disk at the end of a successful acquisition (to save space). Default is
        False.
    """

    def __init__(
        self,
        store: MutableMapping | str | os.PathLike | FSMap | None = None,
        *,
        overwrite: bool = False,
        synchronizer: ZarrSynchronizer | None = None,
        zarr_version: Literal[2, 3, None] = None,
        array_kwargs: ArrayCreationKwargs | None = None,
        minify_attrs_metadata: bool = False,
    ) -> None:
        try:
            import zarr
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "zarr is required to use this handler. Install with `pip install zarr`"
            ) from e

        # main zarr group
        self._group = zarr.group(
            store,
            overwrite=overwrite,
            synchronizer=synchronizer,
            zarr_version=zarr_version,
        )

        # if we don't check this here, we'll get an error when creating the first array
        if (
            not overwrite and any(self._group.arrays()) or self._group.attrs
        ):  # pragma: no cover
            path = self._group.store.path if hasattr(self._group.store, "path") else ""
            raise ValueError(
                f"There is already data in {path!r}. Use 'overwrite=True' to overwrite."
            )

        # local cache of {position index -> zarr.Array}
        # (the group will have a dataset for each position)
        self._arrays: dict[str, zarr.Array] = {}

        # set during sequenceStarted and cleared during sequenceFinished
        self._current_sequence: useq.MDASequence | None = None

        # passed to zarr.group.create
        self._array_kwargs: ArrayCreationKwargs = array_kwargs or {}
        self._array_kwargs.setdefault("dimension_separator", "/")

        self._minify_metadata = minify_attrs_metadata

    @classmethod
    def in_tmpdir(
        cls,
        suffix: str | None = ".zarr",
        prefix: str | None = "pymmcore_zarr_",
        dir: str | PathLike[str] | None = None,
        cleanup_atexit: bool = True,
        **kwargs: Any,
    ) -> OMEZarrWriter:
        """Create OMEZarrHandler that writes to a temporary directory.

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
            Remaining kwargs are passed to `OMEZarrHandler.__init__`
        """
        # same as zarr.storage.TempStore, but with option not to cleanup
        path = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        if cleanup_atexit:

            @atexit.register
            def _atexit_rmtree(_path: str = path) -> None:
                if os.path.isdir(_path):
                    shutil.rmtree(_path)

        return cls(path, **kwargs)

    @property
    def group(self) -> zarr.Group:
        """Read-only access to the zarr group."""
        return self._group

    # The next three methods - `sequenceStarted`, `sequenceFinished`, and `frameReady`
    # are to be connected directly to the MDA's signals, perhaps via listener_connected

    def sequenceStarted(self, seq: useq.MDASequence) -> None:
        """On sequence started, simply store the sequence."""
        self._set_sequence(seq)

    def sequenceFinished(self, seq: useq.MDASequence) -> None:
        """On sequence finished, clear the current sequence."""
        self._current_sequence = None

        if self._minify_metadata:
            self._minify_zattrs_metadata()

    def frameReady(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: dict | None = None
    ) -> None:
        """Write frame to the zarr array for the appropriate position."""
        key = f'{POS_PREFIX}{event.index.get("p", 0)}'
        if key in self._arrays:
            ary = self._arrays[key]
        else:
            # this is the first time we've seen this position
            # create a new Zarr array in the group for it
            if not self._current_sequence:
                # just in case sequenceStarted wasn't called
                self._set_sequence(event.sequence)

            if not (seq := self._current_sequence):
                # This needs to be implemented for cases where we're not executing
                # an MDASequence.  Or, we need to create a better "mock" MDASequence
                # for generic Iterable[MDAEvent]
                raise NotImplementedError(
                    "Writing zarr without a MDASequence not yet implemented"
                )

            # create the new array, getting XY chunksize from the frame
            # and total shape from the sequence
            shape = (
                *tuple(v for k, v in seq.sizes.items() if k != "p" and v > 0),
                *frame.shape,
            )
            axes = (*(k for k in seq.sizes if k != "p"), "y", "x")
            ary = self._new_array(key, shape, frame.dtype, axes)

            # write the MDASequence metadata and xarray _ARRAY_DIMENSIONS to the array
            ary.attrs.update(
                {
                    "useq_MDASequence": json.loads(seq.json(exclude_unset=True)),
                    "_ARRAY_DIMENSIONS": axes,
                }
            )

        # WRITE DATA TO DISK
        index = tuple(event.index.get(k) for k in self._used_axes)
        ary[index] = frame  # for zarr, this immediately writes to disk

        # write frame metadata
        if meta:
            # fix serialization MDAEvent
            # XXX: There is already an Event object in meta, this overwrites it.
            meta["Event"] = json.loads(
                event.json(exclude={"sequence"}, exclude_defaults=True)
            )
        frame_meta = ary.attrs.get("frame_meta", [])
        frame_meta.append(meta or {})
        ary.attrs["frame_meta"] = frame_meta

    # ------------------------------- private --------------------------------

    def _set_sequence(self, seq: useq.MDASequence | None) -> None:
        """Set the current sequence, and update the used axes."""
        self._current_sequence = seq
        if seq:
            self._used_axes = tuple(x for x in seq.used_axes if x != "p")

    def _new_array(
        self, key: str, shape: tuple[int, ...], dtype: np.dtype, axes: tuple[str, ...]
    ) -> zarr.Array:
        """Create a new array in the group, under `key`."""
        self._arrays[key] = ary = self._group.create(
            key,
            shape=shape,
            chunks=(1,) * len(shape[:-2]) + shape[-2:],  # single XY plane chunks
            dtype=dtype,
            **self._array_kwargs,
        )

        # add minimal OME-NGFF metadata
        scales = self._group.attrs.get("multiscales", [])
        scales.append(self._multiscales_item(ary.path, ary.path, axes))
        self._group.attrs["multiscales"] = scales

        return ary

    def _multiscales_item(self, path: str, name: str, axes: Sequence[str]) -> dict:
        """ome-zarr multiscales image metadata.

        https://ngff.openmicroscopy.org/0.4/index.html#multiscale-md
        """
        tforms = [{"scale": [1] * len(axes), "type": "scale"}]
        return {
            "axes": [{"name": ax, "type": AXTYPE.get(ax, "")} for ax in axes],
            "datasets": [{"coordinateTransformations": tforms, "path": path}],
            "name": name,
            "version": "0.4",
        }

    def _minify_zattrs_metadata(self) -> None:
        """Read, minify, and write zattrs metadata to disk.

        Totally optional and just saves a little space since zattrs for arrays can
        get big with all the metadata.

        called during sequenceFinished if `minify_attrs_metadata=True`
        """
        from zarr.util import json_loads

        store = self._group.store
        for key in store.keys():
            if key.endswith(".zattrs"):
                data = json_loads(store[key])
                # dump minified data back to disk
                store[key] = json.dumps(data, separators=(",", ":")).encode("ascii")


# https://ngff.openmicroscopy.org/0.4/index.html#axes-md
AXTYPE = {
    "x": "space",
    "y": "space",
    "z": "space",
    "c": "channel",
    "t": "time",
    "p": "position",
}
