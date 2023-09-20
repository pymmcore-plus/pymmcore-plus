from __future__ import annotations

from typing import TYPE_CHECKING, MutableMapping, Sequence

import useq
from pymmcore_plus import CMMCorePlus, configure_logging
from pymmcore_plus._util import listeners_connected
from useq import MDASequence

if TYPE_CHECKING:
    import numpy as np
    import zarr


POS_PREFIX = "p"
AXTYPE = {
    "x": "space",
    "y": "space",
    "z": "space",
    "c": "channel",
    "t": "time",
    "p": "position",
}


def multiscales_image(path: str, name: str, axes: Sequence[str]) -> dict:
    # make one for each position
    axes = [*axes, "y", "x"]
    scale = [1] * len(axes)
    return {
        "axes": [{"name": ax, "type": AXTYPE.get(ax, "")} for ax in axes],
        "datasets": [
            {
                "coordinateTransformations": [{"scale": scale, "type": "scale"}],
                "path": path,
            },
        ],
        "name": name,
        "version": "0.4",
    }


class OMEZarrHandler:
    def __init__(
        self,
        store_or_group: MutableMapping | str | None | zarr.Group = None,
        overwrite: bool = False,
        *,
        synchronizer=None,
        zarr_version=None,
    ) -> None:
        import zarr

        if isinstance(store_or_group, zarr.Group):
            self._group = store_or_group
        else:
            self._group = zarr.group(
                store_or_group,
                overwrite=overwrite,
                synchronizer=synchronizer,
                zarr_version=zarr_version,
            )

        # we store a map of position index to zarr.Array
        # the group will have a dataset for each position
        self._arrays: dict[str, zarr.Array] = {}
        self._current_sequence: useq.MDASequence | None = None

    def sequenceStarted(self, seq: useq.MDASequence) -> None:
        self._current_sequence = seq
        self._used_axes = tuple(x for x in self._current_sequence.used_axes if x != "p")

    def sequenceFinished(self, seq: useq.MDASequence) -> None:
        self._current_sequence = None

    def frameReady(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: dict | None = None
    ) -> None:
        key = f'{POS_PREFIX}{event.index.get("p", 0)}'
        if key not in self._arrays:
            if not self._current_sequence:
                self._current_sequence = event.sequence
            if not (seq := self._current_sequence):
                raise NotImplementedError(
                    "Writing zarr without a MDASequence not yet implemented"
                )
            shape = (*tuple(v for k, v in seq.sizes.items() if k != "p"), *frame.shape)
            axes = tuple(k for k in seq.sizes if k != "p")
            ary = self._new_array(key, shape, frame.dtype, axes)
        else:
            ary = self._arrays[key]

        index = tuple(event.index.get(k) for k in self._used_axes)
        ary[index] = frame

    @property
    def group(self) -> zarr.Group:
        return self._group

    def _new_array(
        self, key: str, shape: tuple[int, ...], dtype: np.dtype, axes: tuple[str, ...]
    ) -> zarr.Array:
        # a chunk is a single XY plane
        chunks = [1] * len(shape)
        chunks[-2:] = shape[-2:]
        ary = self._group.create(
            key, shape=shape, chunks=chunks, dtype=dtype, dimension_separator="/"
        )
        self._arrays[key] = ary

        scales = self._group.attrs.get("multiscales", [])
        scales.append(multiscales_image(ary.path, ary.path, axes))
        self._group.attrs["multiscales"] = scales

        return ary


sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 1}],
    stage_positions=[{"x": 1, "y": 1, "name": "some position"}, {"x": 0, "y": 0}],
    time_plan={"interval": 0.1, "loops": 5},
    z_plan={"range": 4, "step": 0.5},
    axis_order="tpcz",
)

core = CMMCorePlus.instance()
core.loadSystemConfiguration()
handler = OMEZarrHandler("out.zarr", overwrite=True)
configure_logging(stderr_level="WARNING")
with listeners_connected(core.mda.events, handler):
    core.mda.run(sequence)

print([x.shape for _, x in handler.group.arrays()])
print([x.chunks for _, x in handler.group.arrays()])
