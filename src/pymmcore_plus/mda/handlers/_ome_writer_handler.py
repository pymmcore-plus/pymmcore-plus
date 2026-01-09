"""Handler for writing MDA sequences using the ome-writers library."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeAlias

import numpy as np

if TYPE_CHECKING:
    from pathlib import Path

    import useq

    from pymmcore_plus.metadata import FrameMetaV1, SummaryMetaV1


BackendName: TypeAlias = Literal["acquire-zarr", "tensorstore", "zarr", "tiff"]


class OMEWriterHandler:
    """MDA handler that writes to OME-ZARR or OME-TIFF using ome-writers library.

    This handler wraps the `ome-writers` library to provide a unified interface for
    writing microscopy data in OME formats. It supports multiple backends:

    - "tensorstore": High-performance zarr writing using `tensorstore` backend
    - "acquire-zarr": High-performance zarr writing using `acquire-zarr` backend
    - "zarr": Standard zarr-python backend
    - "tiff": OME-TIFF format using `tifffile` backend
    - "auto": Automatically determine backend based on file extension

    Parameters
    ----------
    path : str | Path
        Path to the output file or directory. File extension determines format:
        - `.zarr` for OME-Zarr
        - `.tif` or `.tiff` for OME-TIFF
    backend : BackendName, optional
        Backend to use for writing. Default is "auto" which infers from path extension.
        Available options are "tensorstore", "acquire-zarr", "zarr", "tiff", and "auto".
    dtype : np.dtype | None, optional
        Data type for the output. If None, inferred from first frame. Default is None.
    overwrite : bool, optional
        Whether to overwrite existing files/directories. Default is False.

    Examples
    --------
    Write to OME-Zarr using tensorstore backend:

    ```python
    from pymmcore_plus import CMMCorePlus
    from pymmcore_plus.mda.handlers import OMEWriterHandler
    from useq import MDASequence

    core = CMMCorePlus.instance()
    core.loadSystemConfiguration()

    sequence = MDASequence(
        channels=["DAPI", "FITC"],
        time_plan={"interval": 2, "loops": 3},
        z_plan={"range": 4, "step": 0.5},
    )

    handler = OMEWriterHandler("output.zarr", backend="tensorstore", overwrite=True)
    core.mda.run(sequence, output=handler)
    ```

    Write to OME-TIFF:

    ```python
    handler = OMEWriterHandler("output.ome.tif", overwrite=True)
    core.mda.run(sequence, output=handler)
    ```
    """

    def __init__(
        self,
        path: str | Path,
        *,
        backend: BackendName | Literal["auto"] = "auto",
        dtype: np.dtype | None = None,
        overwrite: bool = False,
    ) -> None:
        try:
            import ome_writers as omew
        except ImportError as e:
            raise ImportError(
                "ome-writers is required to use this handler. "
                "Install with: pip install ome-writers"
            ) from e

        self._omew = omew

        self._path = str(path)
        self._backend = backend
        self._overwrite = overwrite
        self._dtype = dtype

        self._stream: omew.OMEStream | None = None
        self._current_sequence: useq.MDASequence | None = None

    @property
    def stream(self) -> Any:
        """Return the current ome-writers stream, or None if not initialized."""
        return self._stream

    @property
    def path(self) -> str:
        """Return the output path."""
        return self._path

    def sequenceStarted(self, sequence: useq.MDASequence, meta: SummaryMetaV1) -> None:
        """Initialize the stream when sequence starts."""
        self._current_sequence = sequence

        # Determine dtype from metadata if not provided
        if self._dtype is None:
            # Try to get from metadata, default to uint16
            pixel_type = meta.get("PixelType", "uint16")
            self._dtype = np.dtype(str(pixel_type))

        # Get image dimensions from metadata
        width = meta.get("Width", 512)
        height = meta.get("Height", 512)

        # Convert useq sequence to ome-writers dimensions
        dims = self._omew.dims_from_useq(
            sequence, image_width=width, image_height=height
        )

        # Create the stream
        self._stream = self._omew.create_stream(
            path=self._path,
            dimensions=dims,
            dtype=self._dtype,
            backend=self._backend,
            overwrite=self._overwrite,
        )

    def frameReady(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: FrameMetaV1
    ) -> None:
        """Write frame to the stream."""
        if self._stream is None:
            raise RuntimeError(
                "Stream not initialized. This should not happen - "
                "sequenceStarted should be called first."
            )

        # Simply append the frame - ome-writers handles ordering based on
        # the dimensions and axis_order from the sequence
        self._stream.append(frame)

    def sequenceFinished(self, sequence: useq.MDASequence) -> None:
        """Flush and close the stream when sequence finishes."""
        if self._stream is not None:
            self._stream.flush()
            self._stream = None
        self._current_sequence = None
