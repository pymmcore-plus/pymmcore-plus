from __future__ import annotations

import json
from collections import defaultdict
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar

from ._util import position_sizes

if TYPE_CHECKING:
    import numpy as np
    import useq

    class SupportsSetItem(Protocol):
        def __setitem__(self, key: tuple[int, ...], value: np.ndarray) -> None:
            ...


POS_PREFIX = "p"
T = TypeVar("T", bound="SupportsSetItem")


class OMEWriterBase(Generic[T]):
    def __init__(self) -> None:
        # local cache of {position index -> zarr.Array}
        # (will have a dataset for each position)
        self._arrays: dict[str, T] = {}

        # storage of individual frame metadata
        # maps position key to list of frame metadata
        self._frame_metas: defaultdict[str, list[dict]] = defaultdict(list)

        # set during sequenceStarted and cleared during sequenceFinished
        self._current_sequence: useq.MDASequence | None = None

        # There will be one dict for each position in the sequence. Each dict will
        # contain `{dim: size}` pairs for each dimension in the sequence. Dimensions
        # with no size will be omitted, and 'p' will be removed.
        self._sizes: list[dict[str, int]] = []

    # The next three methods - `sequenceStarted`, `sequenceFinished`, and `frameReady`
    # are to be connected directly to the MDA's signals, perhaps via listener_connected

    def sequenceStarted(self, seq: useq.MDASequence) -> None:
        """On sequence started, simply store the sequence."""
        self._frame_metas.clear()
        self._current_sequence = seq
        if seq:
            self._sizes = position_sizes(seq)

    def sequenceFinished(self, seq: useq.MDASequence) -> None:
        """On sequence finished, clear the current sequence."""
        self.finalize_metadata()
        self._frame_metas.clear()
        self._current_sequence = None
        self._sizes = []

    def frameReady(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: dict | None = None
    ) -> None:
        """Write frame to the zarr array for the appropriate position."""
        # get the position key to store the array in the group
        p_index = event.index.get("p", 0)
        key = f"{POS_PREFIX}{p_index}"
        pos_sizes = self._sizes[p_index]
        if key in self._arrays:
            ary = self._arrays[key]
        else:
            # this is the first time we've seen this position
            # create a new array in the group for it
            if not self._current_sequence:
                # This needs to be implemented for cases where we're not executing
                # an MDASequence.  Or, we need to create a better "mock" MDASequence
                # for generic Iterable[MDAEvent]
                raise NotImplementedError(
                    "Writing OME file without a MDASequence not yet implemented"
                )

            # create the new array, getting XY chunksize from the frame
            # and total shape from the sequence.
            sizes = pos_sizes.copy()
            sizes["y"], sizes["x"] = frame.shape[-2:]
            self._arrays[key] = ary = self.new_array(key, frame.dtype, sizes)

        index = tuple(event.index[k] for k in pos_sizes)
        self.write_frame(ary, index, frame)
        self.store_frame_metadata(key, event, meta)

    def new_array(
        self, position_key: str, dtype: np.dtype, dim_sizes: dict[str, int]
    ) -> T:
        """Create a new array for position_key.

        Parameters
        ----------
        position_key : str
            The position key for the array.
        dtype : np.dtype
            The dtype for the array.
        dim_sizes : dict[str, int]
            Mapping of dimension names to sizes.  This will not be more than 5D
            for OME, and should only include the axis keys "tzcyx".
        """
        raise NotImplementedError("Subclasses must implement this method")

    def write_frame(self, ary: T, index: tuple[int, ...], frame: np.ndarray) -> None:
        # WRITE DATA TO DISK
        ary[index] = frame

    def store_frame_metadata(
        self, key: str, event: useq.MDAEvent, meta: dict | None = None
    ) -> None:
        # needn't be re-implmented in subclasses
        # default implementation is to store the metadata in self._frame_metas
        # use finalize_metadata to write to disk at the end of the sequence.
        if meta:
            # fix serialization MDAEvent
            # XXX: There is already an Event object in meta, this overwrites it.
            event_json = event.json(exclude={"sequence"}, exclude_defaults=True)
            meta["Event"] = json.loads(event_json)
        self._frame_metas[key].append(meta or {})

    def finalize_metadata(self) -> None:
        pass
