from __future__ import annotations

import warnings
from abc import abstractmethod
from collections import defaultdict
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar

from ._util import position_sizes

if TYPE_CHECKING:
    from collections.abc import Mapping

    import numpy as np
    import useq

    from pymmcore_plus.metadata import FrameMetaV1, SummaryMetaV1

    class SupportsSetItem(Protocol):
        def __setitem__(self, key: tuple[int, ...], value: np.ndarray) -> None: ...


_NULL = object()
POS_PREFIX = "p"
T = TypeVar("T", bound="SupportsSetItem")


class _5DWriterBase(Generic[T]):
    """Base class for writers that write 5D data to disk.

    This is a general-purpose writer that can be used for writers that deal strictly
    with a 5D data model (i.e. "tzcyx") such as the OME data model.  On each frameReady
    event, it:

        1. Determines the position being acquired
        2. Calls `new_array` to create one for the position if it doesn't already exist
        3. Determines the index to write the frame at
        4. Calls `write_frame` to write the frame to the array at the index
        5. Calls `store_frame_metadata` to store metadata for the frame.

    Subclasses MUST implement the `new_array` method, which will create a new array to
    hold the full experiment for each position.  Subclasses MAY also override the
    `write_frame` method to customize how the data is written to disk, the
    `finalize_metadata` method to write frame metadata to disk at the end of the
    sequence, and the `store_frame_metadata` method to customize how metadata for each
    frame is stored/handled

    Attributes
    ----------
    position_arrays : dict[str, T]
        Local cache of {position index -> T}, where T is the type of data to be written
        by the writer (for example, `zarr.Array` or a `np.memmap`).  `T` must support
        `__setitem__` for adding frames to a specific index.
    frame_metadatas : defaultdict[str, list[dict]]
        Will accumulate frame metadata for each frame as the experiment progresses.
        It is up to subclasses to do something with it in `finalize_metadata()`, and it
        will be cleared at the end of each sequence.
    current_sequence : useq.MDASequence | None
        The current sequence being written.  This will be set during `sequenceStarted`
        and cleared during `sequenceFinished`.
    position_sizes : list[dict[str, int]]
        There will be one ordered dict, mapping dimension names to size, for each
        position in the sequence. Each dict will contain `{dim: size}` pairs for each
        dimension in the sequence. Dimensions with no size will be omitted, though
        singletons will be included, and 'p' will be removed
    """

    def __init__(self) -> None:
        # local cache of {position index -> zarr.Array}
        # (will have a dataset for each position)
        self.position_arrays: dict[str, T] = {}

        # storage of individual frame metadata
        # maps position key to list of frame metadata
        self.frame_metadatas: defaultdict[str, list[FrameMetaV1]] = defaultdict(list)

        # set during sequenceStarted and cleared during sequenceFinished
        self.current_sequence: useq.MDASequence | None = None

        # list of {dim_name: size} map for each position in the sequence
        self._position_sizes: list[dict[str, int]] = []

        # actual timestamps for each frame
        self._timestamps: list[float] = []

    # The next three methods - `sequenceStarted`, `sequenceFinished`, and `frameReady`
    # are to be connected directly to the MDA's signals, perhaps via listener_connected

    @property
    def position_sizes(self) -> list[dict[str, int]]:
        """Return sizes of each dimension for each position in the sequence.

        Will be a list of dicts, where each dict maps dimension names to sizes, and
        the index in the list corresponds to the stage position index.

        This is the preferred way to access both the dimensions present in each position
        as well as the sizes of those dimensions.

        The dict is ordered, and the order reflects the order of dimensions in the
        shape of each position.
        """
        return self._position_sizes

    def sequenceStarted(
        self, seq: useq.MDASequence, meta: SummaryMetaV1 | object = _NULL
    ) -> None:
        """On sequence started, simply store the sequence."""
        # this is here for backwards compatibility with experimental viewer widget.
        if meta is _NULL:  # pragma: no cover
            warnings.warn(
                "calling `sequenceStarted` without metadata as the second argument is "
                "deprecated and will raise an exception in the future. Please propagate"
                " metadata from the event callback.",
                UserWarning,
                stacklevel=2,
            )
        self.frame_metadatas.clear()
        self.current_sequence = seq
        if seq:
            self._position_sizes = position_sizes(seq)

    def sequenceFinished(self, seq: useq.MDASequence) -> None:
        """On sequence finished, clear the current sequence."""
        self.finalize_metadata()
        self.frame_metadatas.clear()

    def get_position_key(self, position_index: int) -> str:
        """Get the position key for a specific position index.

        This key will be used for subclasses like Zarr that need a directory structure
        for each position.  And may also be used to index into `self.position_arrays`.
        """
        return f"{POS_PREFIX}{position_index}"

    def frameReady(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: FrameMetaV1
    ) -> None:
        """Write frame to the zarr array for the appropriate position."""
        # get the position key to store the array in the group
        p_index = event.index.get("p", 0)
        key = self.get_position_key(p_index)
        pos_sizes = self.position_sizes[p_index]
        if key in self.position_arrays:
            ary = self.position_arrays[key]
        else:
            # this is the first time we've seen this position
            # create a new array in the group for it
            if not self.current_sequence:
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
            self.position_arrays[key] = ary = self.new_array(key, frame.dtype, sizes)

        index = tuple(event.index[k] for k in pos_sizes)
        t = event.index.get("t", 0)
        if t >= len(self._timestamps) and "runner_time_ms" in meta:
            self._timestamps.append(meta["runner_time_ms"])
        self.write_frame(ary, index, frame)
        self.store_frame_metadata(key, event, meta)

    @abstractmethod
    def new_array(
        self, position_key: str, dtype: np.dtype, dim_sizes: dict[str, int]
    ) -> T:
        """Create a new array for position_key.

        Should create a new array for the given position key, with the given dtype and
        dimensions.

        Parameters
        ----------
        position_key : str
            The position key for the array.
        dtype : np.dtype
            The dtype for the array.
        dim_sizes : dict[str, int]
            Ordered mapping of dimension names to sizes.  This will not be more than 5D
            for OME, and should only include the axis keys "tzcyx".
            Example: `{"t": 10, "z": 3, "c": 2, "y": 512, "x": 512}`
        """
        raise NotImplementedError("Subclasses must implement this method")

    def write_frame(self, ary: T, index: tuple[int, ...], frame: np.ndarray) -> None:
        """Write information in `frame` to the datastore `ary` at `index`.

        Subclasses may override this method to customize how the data is written to
        disk.  The default implementation is to simply write the frame to the array at
        the given index with `ary[index] = frame`.  Depending on the type of datastore,
        additional steps may be necessary to flush or sync the data to disk.

        Parameters
        ----------
        ary : T
            The full datastore for a given position.
        index : tuple[int, ...]
            The index to write the frame at.
        frame : np.ndarray
            The incoming frame to write to disk.
        """
        # WRITE DATA TO DISK
        ary[index] = frame

    def store_frame_metadata(
        self, key: str, event: useq.MDAEvent, meta: FrameMetaV1
    ) -> None:
        """Called during each frameReady event to store metadata for the frame.

        Subclasses may override this method to customize how metadata is stored for each
        frame, for example, to write it to disk immediately, or to store it in a
        different format.

        Parameters
        ----------
        key : str
            The position key for the frame (e.g. "p0" for the first position).
        event : useq.MDAEvent
            The event that triggered the frameReady signal.
        meta : dict
            Metadata associated with the frame.
        """
        # needn't be re-implemented in subclasses
        # default implementation is to store the metadata in self._frame_metas
        # use finalize_metadata to write to disk at the end of the sequence.
        self.frame_metadatas[key].append(meta or {})

    def finalize_metadata(self) -> None:
        """Called during sequenceFinished before clearing sequence metadata.

        Subclasses may override this method to flush any accumulated frame metadata to
        disk at the end of the sequence.
        """

    # This syntax is intentionally the same as xarray's isel method.  It's possible
    # we will use xarray in the future, and this will make it easier to switch.
    def isel(
        self,
        indexers: Mapping[str, int | slice] | None = None,
        **indexers_kwargs: int | slice,
    ) -> np.ndarray:
        """Select data from the array.

        This is a convenience method to select data from the array for a given position
        key.  It will call the appropriate `__getitem__` method on the array with the
        given indexers.

        Parameters
        ----------
        indexers : Mapping[str, int | slice] | None
            Mapping of dimension names to indices or slices.  If None, will return the
            full array.
        **indexers_kwargs : int | slice
            Keyword arguments of dimension names to indices or slices.  These will be
            merged with `indexers`, and allows for a nicer syntax.

        Returns
        -------
        np.ndarray
            The selected data from the array.

        Examples
        --------
        >>> data = writer.isel(t=0, z=1, c=0, x=slice(128, 256))
        """
        indexers = dict(indexers or {})
        indexers.update(indexers_kwargs)

        p_index = indexers.get("p", 0)
        if isinstance(p_index, slice):
            raise NotImplementedError("Cannot slice over position index")  # TODO

        try:
            sizes = [*list(self.position_sizes[p_index]), "y", "x"]
        except IndexError as e:
            raise IndexError(
                f"Position index {p_index} out of range for {len(self.position_sizes)}"
            ) from e
        data = self.position_arrays[self.get_position_key(p_index)]
        full = slice(None, None)
        index = tuple(indexers.get(k, full) for k in sizes)
        return data[index]  # type: ignore
