from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ._img_sequence_writer import ImageSequenceWriter
from ._ome_tiff_writer import OMETiffWriter
from ._ome_writer_handler import OMEWriterHandler
from ._ome_zarr_writer import OMEZarrWriter
from ._tensorstore_handler import TensorStoreHandler

if TYPE_CHECKING:
    from pymmcore_plus.mda._runner import Output

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
    path_str = str(path).rstrip("/").rstrip(":") if path else ""

    # Handle "memory://" -> use OMEWriterHandler in temp directory
    if not path or path_str.lower() == "memory":
        return OMEWriterHandler.from_output(out)

    path_resolved = str(Path(path).expanduser().resolve())

    # Zarr or TIFF -> use OMEWriterHandler
    path_lower = path_resolved.lower()
    if path_lower.endswith(".zarr") or path_lower.endswith((".tiff", ".tif")):
        return OMEWriterHandler.from_output(out)

    # No extension - use ImageSequenceWriter
    if not (Path(path_resolved).suffix or Path(path_resolved).exists()):
        return ImageSequenceWriter(path_resolved)

    raise ValueError(f"Could not infer a writer handler for path: '{path}'")


def handler_for_path(path: str | Path, format: str | None = None) -> object:
    """Convert a string or Path into a handler object.

    This method picks from the built-in handlers based on the extension of the path.

    Parameters
    ----------
    path : str | Path
        Path to the output file or directory.
    format : str | None, optional
        Format/backend to use. Default is None which auto-detects from extension.

    Returns
    -------
    object
        A handler object for the specified path.
    """
    from pymmcore_plus.mda._runner import Output

    return handler_for_output(Output(path=path, format=format))  # type: ignore[arg-type]
