from __future__ import annotations

import atexit
import json
import os.path
import shutil
import tempfile
from typing import TYPE_CHECKING, Any, Literal, Mapping, MutableMapping, Protocol

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

        # local cache of {position index -> event keys}
        self._used_axes: dict[str, tuple[str, ...]] = {}

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
        self._current_sequence = seq

    def sequenceFinished(self, seq: useq.MDASequence) -> None:
        """On sequence finished, clear the current sequence."""
        self._current_sequence = None

        if self._minify_metadata:
            self._minify_zattrs_metadata()

    def frameReady(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: dict | None = None
    ) -> None:
        """Write frame to the zarr array for the appropriate position."""
        # get the position key to store the array in the group
        key = f'{POS_PREFIX}{event.index.get("p", 0)}'

        if key in self._arrays:
            ary = self._arrays[key]
        else:
            # this is the first time we've seen this position
            # create a new Zarr array in the group for it
            if not self._current_sequence:
                # just in case sequenceStarted wasn't called
                self._current_sequence = event.sequence

            if not (seq := self._current_sequence):
                # This needs to be implemented for cases where we're not executing
                # an MDASequence. Or, we need to create a better "mock" MDASequence
                # for generic Iterable[MDAEvent]
                raise NotImplementedError(
                    "Writing zarr without a MDASequence not yet implemented"
                )

            # create the new array, getting XY chunksize from the frame
            # and total shape from the sequence. _used_axes below is to store the axes
            # that have been used for each array. we need this because different
            # positions can have a sub-sequence and so the axes can change.
            shape, self._used_axes[key] = self._get_shape_and_axis(event.index, frame)

            # create the array in the group
            ary = self._new_array(key, shape, frame.dtype, self._used_axes[key])

            # write the MDASequence metadata and xarray _ARRAY_DIMENSIONS to the array
            ary.attrs.update(
                {
                    "useq_MDASequence": json.loads(seq.json(exclude_unset=True)),
                    "_ARRAY_DIMENSIONS": self._used_axes[key],
                }
            )

        # WRITE DATA TO DISK
        index = tuple(event.index.get(k) for k in self._used_axes[key])
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

    def _get_shape_and_axis(
        self, index: Mapping[str, int], frame: np.ndarray
    ) -> tuple[tuple[int, ...], tuple[str, ...]]:
        """Get the shape depending on the current position."""
        if not (main_seq := self._current_sequence):
            raise ValueError("Curr ent sequence is not set.")

        # if no positions, just use main sequence shape and axes
        if not main_seq.stage_positions:
            return self._get_main_shape_and_axis(frame)

        # get the current position and position index
        p_idx = index.get("p", 0)
        current_position = main_seq.stage_positions[p_idx]

        if current_position.sequence is not None:
            return self._get_sub_seq_shape_and_axis(frame, current_position.sequence)
        else:
            # if no sub-sequence, just use the main sequence shape and axes
            return self._get_main_shape_and_axis(frame)

    def _get_main_shape_and_axis(
        self, frame: np.ndarray
    ) -> tuple[tuple[int, ...], tuple[str, ...]]:
        """Rerturn the shape and axis of the main sequence."""
        if not self._current_sequence:
            raise ValueError("Current sequence is not set.")
        used_axis = self._used_axis(self._current_sequence)
        shape = tuple(
            v for k, v in self._current_sequence.sizes.items() if k != "p" and v != 0
        )
        return shape + frame.shape, used_axis

    def _get_sub_seq_shape_and_axis(
        self, frame: np.ndarray, sub_sequence: useq.MDASequence
    ) -> tuple[tuple[int, ...], tuple[str, ...]]:
        """Return the shape and axis of a position sub-sequence.

        If the position has a sub-sequence, we need to combine the used axes
        from both the main sequence and the sub-sequence and then calculate the
        shape from that because sub-sequences might not use all the axes of the
        main sequence.

        For example if we have this sequence:

        sequence = MDASequence(
            axis_order="pcz",
            channels=["DAPI"],
            stage_positions=[
                (1, 2, 3),
                {
                    "x": 4,
                    "y": 5,
                    "z": 6,
                    "sequence": MDASequence(
                        grid_plan=GridRowsColumns(rows=2, columns=1)
                    ),
                },
            ],
            z_plan={"range": 3, "step": 1},

        `sequence.used_axes` for the main sequence gives ("c", "z") (excluding "p")
        but for the position with the sub-sequence, `sequence.used_axes` gives ("g",)
        only.

        Therefore, we need to combine the used axes from both the  main sequence and
        the sub-sequence so that the sub-sequence used axis also contains the main axes:
        ("g", "z", "c").

        With this, we can calculate the shape of the array based on both the main
        sequence sizes and the sub-sequence sizes.
        """
        if not self._current_sequence:
            raise ValueError("Current sequence is not set.")

        main_used_axis = self._used_axis(self._current_sequence)
        sub_seq_used_axis = self._used_axis(sub_sequence)

        # here not using the set() function because it doesn't preserve the order
        # updated_used_axis = list(set(sub_seq_used_axis + main_used_axis))
        updated_used_axis = []
        for axis in sub_seq_used_axis + main_used_axis:
            if axis not in updated_used_axis:
                updated_used_axis.append(axis)

        # get the shape of the array by using the main sequence or the sub-sequence
        # sizes
        shape = []
        for ax in updated_used_axis:
            if ax in sub_seq_used_axis:
                shape.append(sub_sequence.sizes[ax])
            else:
                shape.append(self._current_sequence.sizes[ax])

        return tuple(shape) + frame.shape, tuple(updated_used_axis)

    def _used_axis(self, seq: useq.MDASequence) -> tuple[str, ...]:
        """Get the used axes for the current sequence."""
        return tuple(x for x in seq.used_axes if x != "p")

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
