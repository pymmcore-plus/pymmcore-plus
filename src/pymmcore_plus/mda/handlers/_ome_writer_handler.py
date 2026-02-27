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

    from pymmcore_plus.metadata import FrameMetaV1, SummaryMetaV1

ZARR_BACKENDS = ["tensorstore", "acquire-zarr", "zarr-python", "zarrs-python"]
TIFF_BACKEND = "tifffile"

BackendName: TypeAlias = Literal[
    "tensorstore", "acquire-zarr", "zarr-python", "zarrs-python", "tifffile"
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
        - `(.ome).zarr` for OME-ZARR
        - `(.ome).tif` or `(.ome).tiff` for OME-TIFF
    backend : BackendName | Literal["auto"] , optional
        Backend to use for writing. Default is "auto". Available options are
        "tensorstore", "acquire-zarr", "zarr-python", "zarrs-python", "tifffile",
        or "auto".
        - If `path` has a recognized extension (`.zarr`, `.tif`, `.tiff`,
          or their `.ome.*` variants) and `backend` is `"auto"`, the format
          is inferred from the extension.
        - If `path` has no recognized extension and `backend` is `"auto"`,
          `ome-writers` picks the first available backend (typically
          `tensorstore`) and emits a warning.
        - If `backend` is set explicitly, that backend is used regardless of the
          path extension.
    overwrite : bool, optional
        Whether to overwrite existing files/directories. Default is False.

    To create a handler that writes to a temporary directory, you can use the
    `in_tmpdir` class method.

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

    Write to OME-TIFF:
    ```python
    handler = OMEWriterHandler("output.ome.tiff")
    core.mda.run(sequence, output=handler)
    ```

    Write OME-ZARR:
    ```python
    handler = OMEWriterHandler("output.ome.zarr")
    # or, to specify the backend explicitly:
    # handler = OMEWriterHandler("output.ome.zarr", backend="tensorstore")
    core.mda.run(sequence, output=handler)
    ```

    Write OME-TIFF or OME-ZARR to a temporary directory (auto-cleaned on exit):
    ```python
    # to save in a temporary directory (default: `ome.zarr` with `tensorstore` backend):
    handler = OMEWriterHandler.in_tmpdir()
    # or, to specify backend and suffix explicitly:
    handler = OMEWriterHandler.in_tmpdir(backend="tensorstore", suffix=".ome.zarr")
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
                "`path` is required. Use OMEWriterHandler.in_tmpdir() for temporary "
                "directory."
            )

        self._path = path_str
        self._backend = backend
        self._overwrite = overwrite

        self._stream: omew.OMEStream | None = None

        _validate_backend_path_combination(self._path, self._backend)

    @property
    def path(self) -> str:
        """Return the output path."""
        return self._path

    @property
    def stream(self) -> omew.OMEStream | None:
        """Return the current ome-writers stream, or None if not initialized."""
        return self._stream

    @classmethod
    def in_tmpdir(
        cls,
        backend: BackendName = "tensorstore",
        suffix: str = "",
        prefix: str | None = "_pmmcp_tmp_",
        dir: str | PathLike[str] | None = None,
        cleanup_atexit: bool = True,
        **kwargs: Any,
    ) -> Self:
        """Create OMEWriterHandler that writes to a temporary directory.

        Parameters
        ----------
        backend : BackendName , optional
            Backend to use for writing. Default is "tensorstore". Available options are
            "tensorstore", "acquire-zarr", "zarr-python", "zarrs-python", "tifffile".
        suffix : str, optional
            If suffix is specified, the file name will end with that suffix. Empty by
            default, will be determined by backend.
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
            Remaining kwargs are passed to `OMEWriterHandler.__init__` (e.g. overwrite).
        """
        # Determine suffix based on backend if not provided or validate combination
        if not suffix:
            suffix = ".ome.zarr" if backend in ZARR_BACKENDS else ".ome.tiff"
        else:
            _validate_backend_path_combination(suffix, backend)
        # Create a unique temp directory path, then remove the directory
        # because ome-writers expects to create the directory itself
        path = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        os.rmdir(path)  # Remove empty dir so ome-writers can create it
        if cleanup_atexit:
            _register_cleanup_atexit(path)
        return cls(path=path, backend=backend, overwrite=True, **kwargs)

    def sequenceStarted(self, sequence: useq.MDASequence, meta: SummaryMetaV1) -> None:
        """Create the ome-writers stream from sequence and metadata."""
        self._stream = None
        settings = _prepare_stream_settings(
            path=self._path,
            backend=self._backend,
            overwrite=self._overwrite,
            sequence=sequence,
            meta=meta,
        )
        self._stream = omew.create_stream(settings=settings)

    def frameReady(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: FrameMetaV1
    ) -> None:
        """Append a single frame to the stream."""
        if self._stream is not None:
            self._stream.append(frame)
        else:
            raise RuntimeError(
                "Stream is not initialized. Ensure sequenceStarted() is called before "
                "frameReady()."
            )

    def sequenceFinished(self, sequence: useq.MDASequence) -> None:
        """Close the stream when sequence finishes."""
        if self._stream is not None:
            self._stream.close()
            self._stream = None


# --------------------------HELPER FUNCTIONS--------------------------


def _validate_backend_path_combination(
    path: str | Path, backend: BackendName | Literal["auto"]
) -> None:
    """Validate that backend is compatible with the file path extension."""
    path_lower = str(path).lower()

    if backend == "auto":
        return

    is_zarr = path_lower.endswith(".zarr")
    is_tiff = path_lower.endswith((".tif", ".tiff", ".ome.tif", ".ome.tiff"))

    if is_zarr and backend == TIFF_BACKEND:
        raise ValueError(
            f"Backend '{backend}' cannot be used with ZARR path '{path}'. "
            "Use 'tensorstore' or 'acquire-zarr' instead."
        )
    elif is_tiff and backend in ZARR_BACKENDS:
        raise ValueError(
            f"Backend '{backend}' cannot be used with TIFF path "
            f"'{path}'. Use 'tifffile' backend instead."
        )


def _prepare_stream_settings(
    path: str | Path,
    backend: BackendName | Literal["auto"],
    overwrite: bool,
    sequence: useq.MDASequence,
    meta: SummaryMetaV1,
) -> omew.AcquisitionSettings:
    """Prepare the AcquisitionSettings for creating the OMEStream."""
    image_infos = meta.get("image_infos")
    if not image_infos:
        raise ValueError(
            "Metadata must contain 'image_infos' to determine image properties."
        )
    image_info = image_infos[0]
    width = image_info.get("width")
    height = image_info.get("height")
    dtype = image_info.get("dtype")
    pixel_size = image_info.get("pixel_size_um")

    if width is None or height is None or dtype is None:
        raise ValueError(
            "Metadata 'image_infos' must contain 'width', 'height', and 'dtype' keys."
        )

    # Create acquisition settings based on sequence and metadata
    return omew.AcquisitionSettings(
        root_path=str(path),
        dtype=dtype,
        overwrite=overwrite,
        format=backend,
        **omew.useq_to_acquisition_settings(
            sequence,
            image_width=width,
            image_height=height,
            pixel_size_um=pixel_size,
        ),
    )
