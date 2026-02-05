from __future__ import annotations

import tempfile
from pathlib import Path

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
    "handler_for_path",
]


def handler_for_path(path: str | Path) -> object:
    """Convert a string or Path into a handler object.

    This method picks from the built-in handlers based on the extension of the path.
    """
    # for backward compatibility with "memory://"
    if str(path).rstrip("/").rstrip(":").lower() == "memory":
        # Use a temporary path for in-memory storage
        temp_path = Path(tempfile.gettempdir()) / "_pymmcore_plus_tmp.ome.zarr"
        return OMEWriterHandler(temp_path, backend="tensorstore", overwrite=True)

    path = str(Path(path).expanduser().resolve())

    if path.endswith(".zarr"):
        return OMEWriterHandler(path, backend="tensorstore")

    if path.endswith((".tiff", ".tif")):
        return OMEWriterHandler(path, backend="tifffile")

    # FIXME: ugly hack for the moment to represent a non-existent directory
    # there are many features that ImageSequenceWriter supports, and it's unclear
    # how to infer them all from a single string.
    if not (Path(path).suffix or Path(path).exists()):
        return ImageSequenceWriter(path)

    raise ValueError(f"Could not infer a writer handler for path: '{path}'")
