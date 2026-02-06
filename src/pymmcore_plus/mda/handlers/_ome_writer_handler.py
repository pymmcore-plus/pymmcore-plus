"""Handler for writing MDA sequences using the ome-writers library."""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from typing import TYPE_CHECKING, Any, Literal, TypeAlias

import ome_writers as omew

if TYPE_CHECKING:
    from os import PathLike
    from pathlib import Path

    import numpy as np
    import useq
    from typing_extensions import Self

    from pymmcore_plus.mda._runner import Output
    from pymmcore_plus.metadata import FrameMetaV1, SummaryMetaV1

ZARR_BACKENDS = ["tensorstore", "acquire-zarr", "zarr_python", "zarrs_python"]
TIFF_BACKEND = "tifffile"

BackendName: TypeAlias = Literal[
    "tensorstore", "acquire-zarr", "zarr_python", "zarrs_python", "tifffile"
]


def _register_cleanup_atexit(path: str) -> None:
    """Register atexit handler to cleanup directory."""

    @atexit.register
    def _cleanup(_path: str = path) -> None:  # pragma: no cover
        if os.path.isdir(_path):
            shutil.rmtree(_path, ignore_errors=True)


class OMEWriterHandler:
    """MDA handler that writes to OME-ZARR or OME-TIFF using ome-writers library.

    This handler wraps the `ome-writers` library to provide a unified interface for
    writing microscopy data in OME formats.

    Parameters
    ----------
    path : str | Path
        Path to the output file or directory. File extension determines format:
        - `.zarr` for OME-Zarr
        - `.tif` or `.tiff` for OME-TIFF
    backend : BackendName | Literal["auto"] , optional
        Backend to use for writing. Default is "auto" which infers from path extension.
        Available options are  "tensorstore", "acquire-zarr", "zarr_python",
        "zarrs_python", "tifffile" or "auto" (which is the same as None).
    overwrite : bool, optional
        Whether to overwrite existing files/directories. Default is False.

    Alternative constructors are available via classmethods:

    - `OMEWriterHandler.from_output(output)`: Create from an `Output` specification
    - `OMEWriterHandler.in_tmpdir()`: Create handler writing to a temporary directory

    Examples
    --------
    Basic setup (used in all examples below):

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
    ```

    Simplest usage - just provide a path (format auto-detected from extension):

    Write to OME-TIFF:

    ```python
    handler = OMEWriterHandler("output.ome.tiff")
    core.mda.run(sequence, output=handler)
    ```

    Provide path with explicit backend (e.g. for OME Zarr):

    ```python
    handler = OMEWriterHandler("output.ome.zarr", backend="tensorstore")
    core.mda.run(sequence, output=handler)
    ```

    Create from an `Output` specification:

    ```python
    from pymmcore_plus.mda import Output

    out = Output(path="output.ome.zarr", format="tensorstore")
    handler = OMEWriterHandler.from_output(out, overwrite=True)
    core.mda.run(sequence, output=handler)
    ```

    Write to a temporary directory (auto-cleaned on exit):

    ```python
    handler = OMEWriterHandler.in_tmpdir(backend="tensorstore")  # OME Zarr in temp dir
    print(handler.path)  # e.g., /tmp/_pmmcp_tmp_abc123.ome.zarr
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
        path_str = str(path).strip()
        if not path_str:
            raise ValueError(
                "path is required. Use OMEWriterHandler.in_tmpdir() for temporary "
                "directory, or pass 'memory://' to from_output() for temp storage."
            )

        self._path = path_str
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

    @classmethod
    def from_output(cls, out: Output, **kwargs: Any) -> Self:
        """Create OMEWriterHandler from an Output specification.

        Parameters
        ----------
        out : Output
            Output specification with path and format.
        **kwargs
            Additional kwargs passed to `OMEWriterHandler.__init__`.

        Returns
        -------
        OMEWriterHandler
            Handler configured according to the Output specification.
        """
        from pathlib import Path

        path, fmt = out.path, out.format

        # Extract backend from format (could be string or ome-writers Format object)
        backend: BackendName | Literal["auto"] = "auto"
        if isinstance(fmt, str):
            backend = fmt  # type: ignore[assignment]
        elif isinstance(fmt, omew.OmeTiffFormat) or isinstance(fmt, omew.OmeZarrFormat):
            backend = fmt.backend

        # If path has no extension but backend is specified, add appropriate extension
        path_str = str(path)
        if not Path(path_str).suffix and backend is not None:
            if backend in ZARR_BACKENDS:
                path_str = f"{path_str}.ome.zarr"
            elif backend == TIFF_BACKEND:
                path_str = f"{path_str}.ome.tiff"

        return cls(path=path_str, backend=backend, **kwargs)

    @classmethod
    def in_tmpdir(
        cls,
        suffix: str | None = ".ome.zarr",
        prefix: str | None = "_pmmcp_tmp_",
        dir: str | PathLike[str] | None = None,
        cleanup_atexit: bool = True,
        **kwargs: Any,
    ) -> Self:
        """Create OMEWriterHandler that writes to a temporary directory.

        Parameters
        ----------
        suffix : str, optional
            If suffix is specified, the file name will end with that suffix.
            Default is ".ome.zarr".
        prefix : str, optional
            If prefix is specified, the file name will begin with that prefix.
            Default is "_pmmcp_tmp_".
        dir : str or PathLike, optional
            If dir is specified, the file will be created in that directory, otherwise
            a default directory is used (tempfile.gettempdir()).
        cleanup_atexit : bool, optional
            Whether to automatically cleanup the temporary directory when the python
            process exits. Default is True.
        **kwargs
            Remaining kwargs are passed to `OMEWriterHandler.__init__` (e.g. backend,
            overwrite).
        """
        # Create a unique temp directory path, then remove the directory
        # because ome-writers expects to create the directory itself
        path = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        os.rmdir(path)  # Remove empty dir so ome-writers can create it
        if cleanup_atexit:
            _register_cleanup_atexit(path)
        return cls(path=path, overwrite=True, **kwargs)

    def sequenceStarted(self, sequence: useq.MDASequence, meta: SummaryMetaV1) -> None:
        """Initialize the stream when sequence starts."""
        self._current_sequence = sequence

        image_infos = meta.get("image_infos")
        if not image_infos:
            raise ValueError(
                "Metadata must contain 'image_infos' to determine image properties."
            )
        image_info = image_infos[0]

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
        from_useq = omew.useq_to_acquisition_settings(
            sequence,
            image_width=width,
            image_height=height,
            pixel_size_um=pixel_size,
        )

        # Build settings, only include format if explicitly specified
        settings_kwargs: dict[str, Any] = {
            "root_path": self._path,
            "dtype": dtype,
            "overwrite": self._overwrite,
            **from_useq,
        }
        if self._backend is not None:
            settings_kwargs["format"] = self._backend

        settings = omew.AcquisitionSettings(**settings_kwargs)

        self._stream = omew.create_stream(settings=settings)
        # Only zarr backends have _arrays attribute
        backend = getattr(self._stream, "_backend", None)
        if backend is not None and hasattr(backend, "_arrays"):
            self._arrays = backend._arrays  # noqa: SLF001

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
        path_lower = str(self._path).lower()

        if self._backend is None:
            return  # None means auto-detect from path extension

        is_zarr = path_lower.endswith(".zarr")
        is_tiff = path_lower.endswith((".tif", ".tiff", ".ome.tif", ".ome.tiff"))

        if is_zarr and self._backend == TIFF_BACKEND:
            raise ValueError(
                f"Backend 'tifffile' cannot be used with zarr path '{self._path}'. "
                "Use 'tensorstore' or 'acquire-zarr' instead."
            )
        elif is_tiff and self._backend in ZARR_BACKENDS:
            raise ValueError(
                f"Backend '{self._backend}' cannot be used with TIFF path "
                f"'{self._path}'. Use 'tifffile' backend instead."
            )
