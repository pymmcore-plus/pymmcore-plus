"""Protocol and settings for MDA runner handlers."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np
    import ome_writers as omew
    import useq
    from ome_writers._schema import DimensionList, DTypeStr

    from pymmcore_plus.metadata import FrameMetaV1, SummaryMetaV1


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
        Deprecated. Threading is now managed by the MDA runner. This field
        will be removed in a future release.
    queue_maxsize : int
        Deprecated. Threading is now managed by the MDA runner. This field
        will be removed in a future release.
    """

    root_path: str = ""
    format: str = "auto"
    overwrite: bool = False
    dimensions: DimensionList | None = None
    dtype: DTypeStr | None = None
    plate: omew.Plate | None = None
    asynchronous: bool = True
    queue_maxsize: int = 100

    def __post_init__(self) -> None:
        if not self.asynchronous:
            warnings.warn(
                "StreamSettings.asynchronous is deprecated and has no effect. "
                "Threading is now managed by the MDA runner. "
                "This field will be removed in a future release.",
                DeprecationWarning,
                stacklevel=2,
            )
        if self.queue_maxsize != 100:
            warnings.warn(
                "StreamSettings.queue_maxsize is deprecated and has no effect. "
                "Threading is now managed by the MDA runner. "
                "This field will be removed in a future release.",
                DeprecationWarning,
                stacklevel=2,
            )
