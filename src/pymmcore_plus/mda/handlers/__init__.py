from __future__ import annotations

from logging import warning
from pathlib import Path

from pymmcore_plus.mda._runner import Output

from ._img_sequence_writer import ImageSequenceWriter
from ._ome_tiff_writer import OMETiffWriter
from ._ome_writer_handler import OMEWriterHandler
from ._ome_zarr_writer import OMEZarrWriter
from ._tensorstore_handler import TensorStoreHandler

__all__ = [
    "ImageSequenceWriter",
    "OMETiffWriter",
    "OMEWriterHandler",
    "OMEZarrWriter",
    "TensorStoreHandler",
    "handler_for_output",
    "handler_for_path",
]


def handler_for_output(out: Output) -> object:
    """Create a handler from an Output specification.

    Parameters
    ----------
    out : Output
        Output specification with path and format.

    Returns
    -------
    object
        A handler object for the specified output.
    """
    path = out.path
    path_str = str(path).rstrip("/").rstrip(":")

    # Handle "memory://" -> use TensorStoreHandler for backward compatibility
    if path_str.lower() == "memory":
        return TensorStoreHandler()

    path_resolved = str(Path(path).expanduser().resolve())

    # Zarr or TIFF -> use OMEWriterHandler
    path_lower = path_resolved.lower()
    if path_lower.endswith(".zarr") or path_lower.endswith((".tiff", ".tif")):
        return OMEWriterHandler.from_output(out)

    # No extension - use ImageSequenceWriter
    if not (Path(path_resolved).suffix or Path(path_resolved).exists()):
        return ImageSequenceWriter(path_resolved)

    raise ValueError(f"Could not infer a writer handler for path: '{path}'")


def handler_for_path(path: str | Path) -> object:
    """Convert a string or Path into a handler object.

    Deprecated: This function is deprecated and will be removed in a future release.
    Use `handler_for_output` instead.
    """
    warning(
        "`handler_for_path` is deprecated and will be removed in a future release. "
        "Use `handler_for_output` instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return handler_for_output(Output(path=path))
