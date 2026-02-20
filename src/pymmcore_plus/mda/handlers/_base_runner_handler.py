"""Protocol and settings for MDA runner handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np
    import ome_writers as omew
    import useq
    from ome_writers._schema import DimensionList, DTypeStr

    from pymmcore_plus.metadata import FrameMetaV1, SummaryMetaV1

_STOP = object()


@runtime_checkable
class BaseRunnerHandler(Protocol):
    """Protocol for MDA runner handlers."""

    def prepare(self, sequence: useq.MDASequence, meta: SummaryMetaV1 | None) -> None:
        """Prepare the handler for the acquisition."""
        ...

    def writeframe(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: FrameMetaV1
    ) -> None:
        """Write a single frame to the output."""
        ...

    def cleanup(self) -> None:
        """Cleanup resources when acquisition finishes."""
        ...


@dataclass
class StreamSettings:
    """Settings for the OMERunnerHandler.

    Parameters
    ----------
    root_path : str
        Root output path for the acquisition data.
    format : str
        Output format/backend (e.g. ``'ome-tiff'``, ``'ome-zarr'``,
        ``'tensorstore'``). Default is ``'auto'``.
    overwrite : bool
        Whether to overwrite existing data at *root_path*. Default is False.
    dimensions : tuple or None
        Ordered list of acquisition dimensions. If None, derived from the
        MDASequence at runtime.
    dtype : str or None
        Pixel data type (e.g. ``'uint16'``). If None, derived from metadata.
    plate : omew.Plate or None
        Optional plate layout for OME metadata.
    asynchronous : bool
        If True, frames are enqueued and written in a background thread,
        decoupling I/O from the MDA loop. Default is True.
    queue_maxsize : int
        Maximum number of frames to hold in the write queue when
        *asynchronous* is True. Default is 100.
    """

    root_path: str = ""
    format: str = "auto"
    overwrite: bool = False
    dimensions: DimensionList | None = None
    dtype: DTypeStr | None = None
    plate: omew.Plate | None = None
    asynchronous: bool = True
    queue_maxsize: int = 100
