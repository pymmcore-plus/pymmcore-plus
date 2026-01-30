"""Handler for writing MDA sequences using the ome-writers library."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, Literal, TypeAlias

import useq

if TYPE_CHECKING:
    from pathlib import Path

    import numpy as np
    import ome_writers as omew

    from pymmcore_plus.metadata import FrameMetaV1, SummaryMetaV1


BackendName: TypeAlias = Literal[
    "acquire-zarr", "tensorstore", "zarrs-python", "zarr-python", "tifffile"
]


class OMEWriterHandler:
    """MDA handler that writes to OME-ZARR or OME-TIFF using ome-writers library.

    This handler wraps the `ome-writers` library to provide a unified interface for
    writing microscopy data in OME formats. It supports multiple backends:

    - "tensorstore": High-performance zarr writing using `tensorstore` backend
    - "acquire-zarr": High-performance zarr writing using `acquire-zarr` backend
    - "zarr-python": Standard zarr writing using `zarr-python` library
    - "zarrs-python": Standard zarr writing using using `zarrs-python` library
    - "tifffile": OME-TIFF writing using `tifffile` library
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
        Available options are "tensorstore", "acquire-zarr", "zarr-python",
        "zarrs-python", "tifffile", and "auto".
    dtype : str | None, optional
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

        # Get pixel size from metadata (optional)
        pixel_size = image_info.get("pixel_size_um")

        # Get z pixel size from sequence
        z_units: dict[str, tuple[float, str]] = {}
        if sequence.z_plan is not None:
            with contextlib.suppress(AttributeError):
                z_units = {"z": (sequence.z_plan.step, "micrometer")}

        # Convert useq sequence to ome-writers dimensions
        dims = self._omew.dims_from_useq(
            sequence,
            image_width=width,
            image_height=height,
            units=z_units,
            pixel_size_um=pixel_size,
        )

        from rich import print
        print(dims)


        # Convert useq plate to ome-writers plate
        plate: omew.Plate | None = None
        if isinstance(sequence.stage_positions, useq.WellPlatePlan):
            plate = _useq_plate_to_omew(sequence.stage_positions)

        # Create acquisition settings and stream
        settings = self._omew.AcquisitionSettings(
            root_path=self._path,
            dimensions=dims,
            plate=plate,
            dtype=_dtype,
            backend=self._backend,
            overwrite=self._overwrite,
        )
        self._stream = self._omew.create_stream(settings)

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


# ---------------HELPER FUNCTION----------------- #
# TODO: maybe move it to ome-writers?


def _useq_plate_to_omew(useq_plate: useq.WellPlatePlan) -> Any:
    """Convert a useq WellPlatePlan to an ome-writers Plate.

    Parameters
    ----------
    omew_module : module
        The ome_writers module.
    useq_plate : useq.WellPlatePlan
        The useq WellPlatePlan to convert.

    Returns
    -------
    omew_module.Plate
        The converted ome-writers Plate.
    """
    import re

    import ome_writers as omew

    plate = useq_plate.plate
    well_names = plate.all_well_names

    # Extract row names from first column (e.g., A1, B1, C1... -> A, B, C...)
    row_names = []
    for name in well_names[:, 0]:
        match = re.match(r"^([A-Za-z]+)", str(name))
        if match:
            row_names.append(match.group(1))

    # Extract column names from first row (e.g., A1, A2, A3... -> 1, 2, 3...)
    column_names = []
    for name in well_names[0, :]:
        match = re.search(r"(\d+)$", str(name))
        if match:
            column_names.append(match.group(1))

    return omew.Plate(
        row_names=row_names,
        column_names=column_names,
        name=plate.name or None,
    )
