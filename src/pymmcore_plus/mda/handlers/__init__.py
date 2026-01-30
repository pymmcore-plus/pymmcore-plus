from __future__ import annotations

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
    # TODO: "memory://" path is not yet supported by ome-writers tensorstore backend
    if str(path).rstrip("/").rstrip(":").lower() == "memory":
        # For memory stores, use TensorStoreHandler
        return TensorStoreHandler(kvstore="memory://")

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
