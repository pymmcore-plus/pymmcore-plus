from __future__ import annotations

import threading
import time
import warnings
from typing import (
    TYPE_CHECKING,
    Any,
    Deque,
    Literal,
    MutableMapping,
    Protocol,
    Sequence,
    TypedDict,
)

import numpy as np
import useq
from psygnal import Signal
from pymmcore_plus import CMMCorePlus
from pymmcore_plus._util import listeners_connected
from useq import MDASequence

if TYPE_CHECKING:
    from collections import deque
    from typing import ContextManager

    import zarr
    from numcodecs.abc import Codec

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
AXTYPE = {
    "x": "space",
    "y": "space",
    "z": "space",
    "c": "channel",
    "t": "time",
    "p": "position",
}


class OMEZarrHandler:
    """Write an MDA to a zarr file following the ngff spec.

    This implements v0.4
    https://ngff.openmicroscopy.org/0.4/index.html

    Parameters
    ----------
    store_or_group : MutableMapping | str | None | zarr.Group
        The zarr store or `zarr.Group` to write to. If a string, it will be passed to
        `zarr.group` to create a group. If None, a new in-memory group will be
        created.
    overwrite : bool
        Whether to overwrite an existing group. (ignored if passing a `zarr.Group`)
    synchronizer
        Array synchronizer passed to `zarr.group`. (ignored if passing a `zarr.Group`)
    zarr_version
        Zarr version passed to `zarr.group`. (ignored if passing a `zarr.Group`)
    dimension_separator : str
        Separator placed between the dimensions of a chunk in each Array.
        Default is `"/"`.
    """

    def __init__(
        self,
        store_or_group: MutableMapping | str | None | zarr.Group = None,
        *,
        overwrite: bool = False,
        synchronizer: ZarrSynchronizer | None = None,
        zarr_version: Literal[2, 3, None] = None,
        array_kwargs: ArrayCreationKwargs | None = None,
    ) -> None:
        try:
            import zarr
        except ImportError as e:
            raise ImportError(
                "zarr is required to use this handler. Install with `pip install zarr`"
            ) from e

        if isinstance(store_or_group, zarr.Group):
            if overwrite or synchronizer or zarr_version:
                warnings.warn(  # pragma: no cover
                    "overwrite, synchronizer, and zarr_version are ignored"
                    " when passing a zarr.Group",
                    stacklevel=2,
                )

            self._group = store_or_group
        else:
            self._group = zarr.group(
                store_or_group,
                overwrite=overwrite,
                synchronizer=synchronizer,
                zarr_version=zarr_version,
            )

        # if we don't check this here, we'll get an error when creating the first array
        if not overwrite and any(self._group.arrays()) or self._group.attrs:
            path = self._group.store.path if hasattr(self._group.store, "path") else ""
            raise ValueError(
                f"There is already data in {path!r}. Use 'overwrite=True' to overwrite."
            )

        # we store a map of position index to zarr.Array
        # the group will have a dataset for each position
        self._arrays: dict[str, zarr.Array] = {}
        self._current_sequence: useq.MDASequence | None = None

        self._array_kwargs: ArrayCreationKwargs = array_kwargs or {}
        self._array_kwargs.setdefault("dimension_separator", "/")

    def sequenceStarted(self, seq: useq.MDASequence) -> None:
        self._current_sequence = seq
        self._used_axes = tuple(x for x in self._current_sequence.used_axes if x != "p")

    def sequenceFinished(self, seq: useq.MDASequence) -> None:
        self._current_sequence = None

    def frameReady(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: dict | None = None
    ) -> None:
        key = f'{POS_PREFIX}{event.index.get("p", 0)}'
        if key in self._arrays:
            ary = self._arrays[key]
        else:
            if not self._current_sequence:
                self._current_sequence = event.sequence
            if not (seq := self._current_sequence):
                raise NotImplementedError(
                    "Writing zarr without a MDASequence not yet implemented"
                )
            shape = (*tuple(v for k, v in seq.sizes.items() if k != "p"), *frame.shape)
            axes = tuple(k for k in seq.sizes if k != "p")
            ary = self._new_array(key, shape, frame.dtype, axes)

        index = tuple(event.index.get(k) for k in self._used_axes)
        ary[index] = frame

    @property
    def group(self) -> zarr.Group:
        return self._group

    def _new_array(
        self, key: str, shape: tuple[int, ...], dtype: np.dtype, axes: tuple[str, ...]
    ) -> zarr.Array:
        self._arrays[key] = ary = self._group.create(
            key,
            shape=shape,
            chunks=(1,) * len(shape[:-2]) + shape[-2:],  # single XY plane chunks
            dtype=dtype,
            **self._array_kwargs,
        )

        scales = self._group.attrs.get("multiscales", [])
        scales.append(self._multiscales_item(ary.path, ary.path, axes))
        self._group.attrs["multiscales"] = scales

        return ary

    def _multiscales_item(self, path: str, name: str, axes: Sequence[str]) -> dict:
        """ome-zarr multiscales image metadata

        https://ngff.openmicroscopy.org/0.4/index.html#multiscale-md
        """
        # make one for each position
        axes = [*axes, "y", "x"]
        tforms = [{"scale": [1] * len(axes), "type": "scale"}]
        return {
            "axes": [{"name": ax, "type": AXTYPE.get(ax, "")} for ax in axes],
            "datasets": [{"coordinateTransformations": tforms, "path": path}],
            "name": name,
            "version": "0.4",
        }


class ThreadedHandler:
    frameReady = Signal(np.ndarray, useq.MDAEvent, dict)

    def __init__(self) -> None:
        self._deque: deque[tuple | None] = Deque()

    def sequenceStarted(self) -> None:
        self.thread = threading.Thread(target=self.watch_queue)
        self.thread.start()

    def _frameReady(self, *args: Any) -> None:
        self._deque.append(args)

    def sequenceFinished(self) -> None:
        self._deque.append(None)
        self.thread.join()

    def watch_queue(self) -> None:
        while True:
            try:
                args = self._deque.popleft()
            except IndexError:
                time.sleep(0.001)
            if args is None:
                break
            self.frameReady.emit(*args)


sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 1}],
    # stage_positions=[{"x": 1, "y": 1, "name": "some position"}, {"x": 0, "y": 0}],
    time_plan={"interval": 0.1, "loops": 5},
    z_plan={"range": 4, "step": 0.5},
    axis_order="tpcz",
)

core = CMMCorePlus.instance()
core.loadSystemConfiguration()

thread_relay = ThreadedHandler()

handler = OMEZarrHandler("out.zarr", overwrite=True)


with listeners_connected(core.mda.events, handler):
    core.mda.run(sequence)
