"""Handler for writing MDA sequences using the ome-writers library."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeAlias

if TYPE_CHECKING:
    from pathlib import Path

    import numpy as np
    import ome_writers as omew
    import useq

    from pymmcore_plus.metadata import FrameMetaV1, SummaryMetaV1


BackendName: TypeAlias = Literal[
    "acquire-zarr", "tensorstore", "tifffile", "zarr_python", "zarrs_python"
]


class OMEWriterHandler:
    """MDA handler that writes to OME-ZARR or OME-TIFF using ome-writers library.

    This handler wraps the `ome-writers` library to provide a unified interface for
    writing microscopy data in OME formats. It supports multiple backends:

    - "tensorstore": High-performance zarr writing using `tensorstore` backend
    - "acquire-zarr": High-performance zarr writing using `acquire-zarr` backend
    - "tiff": OME-TIFF writing using `tifffile` library
    - "auto": Automatically select backend based on the file extension and available
      libraries

    Parameters
    ----------
    path : str | Path
        Path to the output file or directory. File extension determines format:
        - `.zarr` for OME-Zarr
        - `.tif` or `.tiff` for OME-TIFF
    backend : BackendName, optional
        Backend to use for writing. Default is "auto" which infers from path extension.
        Available options are "tensorstore", "acquire-zarr", "tiff", and "auto".
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

        self._stream: omew.OMEStream | None = None
        self._current_sequence: useq.MDASequence | None = None
        self._arrays: list = []

        # Validate backend matches path extension
        self._validate_backend_path_combination()

    @property
    def stream(self) -> Any:
        """Return the current ome-writers stream, or None if not initialized."""
        return self._stream

    @property
    def path(self) -> str:
        """Return the output path."""
        return self._path

    @property
    def arrays(self) -> list:
        """Return the list of arrays written (for debugging purposes)."""
        return self._arrays

    def sequenceStarted(self, sequence: useq.MDASequence, meta: SummaryMetaV1) -> None:
        """Initialize the stream when sequence starts."""
        self._current_sequence = sequence

        image_info = meta.get("image_infos")
        if image_info is None:
            raise ValueError(
                "Metadata must contain 'image_infos' to determine image properties."
            )
        image_info = image_info[0]

        # Get dtype from metadata
        _dtype = image_info.get("dtype")
        if _dtype is None:
            raise ValueError(
                "Data type not specified and could not be inferred from metadata."
            )

        # Get image dimensions from metadata
        width = image_info.get("width")
        height = image_info.get("height")
        if width is None or height is None:
            raise ValueError(
                "Metadata 'image_infos' must contain 'width' and 'height' keys."
            )

        # Get dtype from metadata
        dtype = image_info.get("dtype")
        if dtype is None:
            raise ValueError(
                "Data type not specified and could not be inferred from metadata."
            )

        # Get pixel size from metadata
        pixel_size = image_info.get("pixel_size_um")

        # Convert useq sequence to ome-writers dimensions
        from_useq = self._omew.useq_to_acquisition_settings(
            sequence,
            image_width=width,
            image_height=height,
            pixel_size_um=pixel_size,
        )

        settings = self._omew.AcquisitionSettings(
            root_path=self._path,
            dtype=dtype,
            overwrite=self._overwrite,
            format=self._backend,
            **from_useq,
        )

        self._stream = self._omew.create_stream(settings=settings)
        self._arrays = self._stream._backend._arrays  # noqa: SLF001  # type: ignore

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
        """Close the stream when sequence finishes."""
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        self._current_sequence = None

    def _validate_backend_path_combination(self) -> None:
        """Validate that backend is compatible with the file path extension."""
        if self._backend == "auto":
            return  # Auto mode will determine the correct backend

        path_lower = str(self._path).lower()
        is_zarr = path_lower.endswith(".zarr")
        is_tiff = path_lower.endswith((".tif", ".tiff", ".ome.tif", ".ome.tiff"))

        if is_zarr and self._backend == "tifffile":
            raise ValueError(
                f"Backend 'tifffile' cannot be used with zarr path '{self._path}'. "
                "Use 'tensorstore' or 'acquire-zarr' instead."
            )
        elif is_tiff and self._backend in (
            "tensorstore",
            "acquire-zarr",
            "zarr_python",
            "zarrs_python",
        ):
            raise ValueError(
                f"Backend '{self._backend}' cannot be used with TIFF path "
                f"'{self._path}'. Use 'tifffile' backend instead."
            )
        elif not (is_zarr or is_tiff):
            # Warn if path doesn't have a recognized extension
            import warnings

            warnings.warn(
                f"Path '{self._path}' does not have a recognized extension "
                "(.zarr, .tif, .tiff). This may cause issues.",
                UserWarning,
                stacklevel=3,
            )
