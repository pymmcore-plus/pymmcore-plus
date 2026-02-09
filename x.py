# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pymmcore-plus[io]",
#     "useq-schema",
#     "yaozarrs",
#     "ome-types",
#     "ndv[qt,vispy]",
# ]
#
# [tool.uv.sources]
# pymmcore-plus = { path = "." }
# ///
"""Test script for OME writer handlers.

Usage:
    uv run x.py [BACKEND...] [OPTION]

Arguments:
    BACKEND: One or more backend names (tensorstore, acquire-zarr, zarr_python,
             zarrs_python, tifffile, tiff-sequence). Multiple backends create
             multiple outputs.

    OPTION: Handler integration method (default: 1)
        - 1: Manual signal connections (sequenceStarted, frameReady, sequenceFinished)
        - 2: Pass handler object(s) to mmc.mda.run(output=handler)
        - 3: Pass Output object(s) to mmc.mda.run(output=Output(path, format))
        - 4: Pass path string(s) to mmc.mda.run(output=path)
        - 5: Create in temporary directory using OMEWriterHandler.in_tmpdir()

Examples
--------
    uv run x.py tensorstore 1              # Single tensorstore output
    uv run x.py tifffile 2                 # Single tifffile output
    uv run x.py tensorstore tifffile 3     # Both tensorstore and tifffile
    uv run x.py tensorstore zarr_python tifffile 4  # Three outputs
"""

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import useq
import yaozarrs
from ome_types import from_tiff

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import Output
from pymmcore_plus.mda.handlers import OMEWriterHandler
from pymmcore_plus.mda.handlers._img_sequence_writer import ImageSequenceWriter

# ==================== CONFIGURATION ====================
# Output directory on desktop - create timestamped subdirectory for each run
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = Path.home() / "Desktop" / "pymmcore_writers" / timestamp
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Sequence
seq = useq.MDASequence(
    axis_order="pcz",
    channels=["DAPI", "FITC"],
    z_plan={"range": 2, "step": 1.0},
    stage_positions=useq.WellPlatePlan(
        plate=useq.WellPlate.from_str("96-well"),
        a1_center_xy=(0, 0),
        selected_wells=((0, 1), (0, 1)),
        well_points_plan=useq.GridRowsColumns(rows=2, columns=2),
    ),
)
# =======================================================


# Parse backends and option from command line
# All args except the last one are backends, last arg is the option number
VALID_BACKENDS = [
    "tensorstore",
    "acquire-zarr",
    "zarr-python",
    "zarrs-python",
    "tifffile",
    "tiff-sequence",
]

if len(sys.argv) < 2:
    # Default: single tensorstore backend, option 1
    BACKENDS = ["tensorstore"]
    OPTION = 1
else:
    # Last argument is the option number, everything before is backends
    try:
        OPTION = int(sys.argv[-1])
        BACKENDS = sys.argv[1:-1] if len(sys.argv) > 2 else [sys.argv[1]]
    except ValueError:
        # If last arg is not a number, treat all args as backends, use option 1
        BACKENDS = sys.argv[1:]
        OPTION = 1

# Validate backends
for backend in BACKENDS:
    if backend not in VALID_BACKENDS:
        raise ValueError(
            f"Invalid backend: {backend}. Valid: {', '.join(VALID_BACKENDS)}"
        )

# =======================================================


def validate_output(path: str | list[str], fmt: str | list[str]) -> None:
    """Validate the output file or directory."""
    # Normalize to lists
    paths = [path] if isinstance(path, str) else path
    fmts = [fmt] if isinstance(fmt, str) else fmt

    # If only one format provided, use it for all paths
    if len(fmts) == 1 and len(paths) > 1:
        fmts = fmts * len(paths)

    for p, f in zip(paths, fmts):
        # All zarr backends create zarr stores
        if f in ("tensorstore", "acquire-zarr", "zarr-python", "zarrs-python"):
            yaozarrs.validate_zarr_store(p)
            print(f"✓ Zarr store ({f} backend) is valid: {p}")
        elif f == "tifffile":
            # For tifffile, look for position files: base_p*.ome.tiff
            # Remove all extensions to get base name
            base_name = Path(p).name
            while "." in base_name:
                base_name = Path(base_name).stem
            files = list(Path(p).parent.glob(f"{base_name}_p*.ome.tiff"))
            if not files:
                # Single file case
                from_tiff(p)
                print(f"✓ TIFF file is valid: {p}")
            else:
                for idx, file in enumerate(sorted(files)):
                    from_tiff(file)
                    print(f"✓ TIFF file {idx} is valid: {file}")
        elif f == "tiff-sequence":
            # Image sequence - just check directory exists and has files
            if Path(p).is_dir():
                files = list(Path(p).glob("*.tif*"))
                print(f"✓ Image sequence directory is valid: {p} ({len(files)} files)")


# Setup core
mmc = CMMCorePlus.instance()
mmc.loadSystemConfiguration()
mmc.setProperty("Objective", "Label", "Nikon 20X Plan Fluor ELWD")

# Configure Outputs for each backend
ZARR_BACKENDS = ["tensorstore", "acquire-zarr", "zarr-python", "zarrs-python"]
handler = None
outputs = []

for idx, backend in enumerate(BACKENDS):
    suffix = f"_{idx}" if len(BACKENDS) > 1 else ""

    if backend in ZARR_BACKENDS:
        outputs.append(
            Output(f"{OUTPUT_DIR}/test{OPTION}{suffix}.ome.zarr", format=backend)
        )
    elif backend == "tifffile":
        outputs.append(
            Output(f"{OUTPUT_DIR}/test{OPTION}{suffix}.ome.tiff", format="tifffile")
        )
    elif backend == "tiff-sequence":
        outputs.append(Output(f"{OUTPUT_DIR}/test{OPTION}_sequence{suffix}"))

# Use single output if only one backend, otherwise use list
output = outputs[0] if len(outputs) == 1 else outputs


# Run based on OPTION
if OPTION == 1:
    # Option 1: Manual signal connections
    handlers = []
    outputs_list = outputs if isinstance(outputs, list) else [outputs]
    for out in outputs_list:
        # Check if it's a sequence directory (no .ome extension)
        if "sequence" in str(out.path) or not (
            str(out.path).endswith(".ome.zarr") or str(out.path).endswith(".ome.tiff")
        ):
            handler = ImageSequenceWriter(out.path, overwrite=True)
        else:
            handler = OMEWriterHandler(out.path, backend=out.format, overwrite=True)
        handlers.append(handler)

    # Connect all handlers
    for handler in handlers:
        mmc.mda.events.sequenceStarted.connect(handler.sequenceStarted)
        mmc.mda.events.frameReady.connect(handler.frameReady)
        mmc.mda.events.sequenceFinished.connect(handler.sequenceFinished)

    mmc.mda.run(seq)

elif OPTION == 2:
    # Option 2: Pass handler object(s) directly to output
    handlers = []
    outputs_list = outputs if isinstance(outputs, list) else [outputs]
    for out in outputs_list:
        # Check if it's a sequence directory (no .ome extension)
        if "sequence" in str(out.path) or not (
            str(out.path).endswith(".ome.zarr") or str(out.path).endswith(".ome.tiff")
        ):
            handler = ImageSequenceWriter(out.path, overwrite=True)
        else:
            handler = OMEWriterHandler(out.path, backend=out.format, overwrite=True)
        handlers.append(handler)

    mmc.mda.run(seq, output=handlers if len(handlers) > 1 else handlers[0])

elif OPTION == 3:
    # Option 3: Pass Output object(s)
    mmc.mda.run(seq, output=output)

elif OPTION == 4:
    # Option 4: Pass path string(s)
    paths = [out.path for out in (outputs if isinstance(outputs, list) else [outputs])]
    mmc.mda.run(seq, output=paths if len(paths) > 1 else paths[0])

elif OPTION == 5:
    # Option 5: Create in temporary directory using OMEWriterHandler.in_tmpdir()
    handler = OMEWriterHandler.in_tmpdir(backend=BACKENDS[0], cleanup_atexit=False)
    print(f"Using temporary directory for output: {handler.path}")
    mmc.mda.run(seq, output=handler)

# Validate outputs
validation_paths = []
validation_formats = []

if OPTION == 5:
    # For OPTION 5, validate the temporary directory created by in_tmpdir()
    validation_paths.append(handler.path)  # type: ignore
    validation_formats.append(BACKENDS[0])
else:
    outputs_list = outputs if isinstance(outputs, list) else [outputs]
    for idx, out in enumerate(outputs_list):
        validation_paths.append(str(out.path))
        # Use the backend from BACKENDS list to determine format
        backend = BACKENDS[idx] if idx < len(BACKENDS) else BACKENDS[0]
        validation_formats.append(backend)

validate_output(validation_paths, validation_formats)

if OPTION == 5:
    # Cleanup temporary directory after validation
    if os.path.isdir(handler.path):  # type: ignore
        shutil.rmtree(handler.path, ignore_errors=True)  # type: ignore
        print(f"✓ Cleaned up temporary directory: {handler.path}")  # type: ignore


class PositionDataWrapper:
    """DataWrapper for ndv that exposes positions as a dimension with slider."""

    def __init__(self, arrays: dict[int, Any]) -> None:
        """Initialize with dictionary mapping position index to array/path.

        Parameters
        ----------
        arrays : dict[int, Any]
            Dictionary mapping position index to array-like object or path string.
        """
        self._arrays_dict = arrays
        self._loaded_arrays: dict[int, Any] = {}
        self._positions = sorted(arrays.keys())

        if not self._positions:
            raise ValueError("No positions in arrays dictionary")

        # Load first position to get shape/dtype info
        self._sample_array = self._load_array(self._positions[0])

    def _load_array(self, pos_idx: int) -> Any:
        """Load array for a given position index (lazy loading)."""
        if pos_idx in self._loaded_arrays:
            return self._loaded_arrays[pos_idx]

        ary = self._arrays_dict.get(pos_idx)
        if ary is None:
            raise ValueError(f"Position {pos_idx} not found in arrays")

        # Convert string paths to array-like objects
        if isinstance(ary, str):
            import zarr

            if ary.endswith(".zarr"):
                ary = zarr.open(ary, mode="r")
            else:
                raise ValueError(
                    f"Unsupported array type for position {pos_idx}: {type(ary)}"
                )

        self._loaded_arrays[pos_idx] = ary
        return ary

    @property
    def shape(self) -> tuple[int, ...]:
        """Return shape with position as first dimension."""
        return (len(self._positions), *self._sample_array.shape)

    @property
    def dtype(self):
        """Return dtype from sample array."""
        return self._sample_array.dtype

    @property
    def ndim(self) -> int:
        """Return number of dimensions (positions + array dims)."""
        return len(self.shape)

    def __array__(self) -> Any:
        """Convert to numpy array (loads all data - use with caution!)."""
        import numpy as np

        # Load all positions and stack them
        arrays = [self._load_array(idx)[...] for idx in self._positions]
        return np.stack(arrays, axis=0)

    def __getitem__(self, key: Any) -> Any:
        """Get data slice, handling position indexing."""
        # Normalize key to tuple
        if not isinstance(key, tuple):
            key = (key,)

        # First index is position
        pos_key = key[0]

        # Handle different position indexing types
        if isinstance(pos_key, int):
            # Single position
            pos_idx = self._positions[pos_key]
            ary = self._load_array(pos_idx)
            # Apply remaining indices to the array
            if len(key) > 1:
                return ary[key[1:]]
            return ary[...]

        elif isinstance(pos_key, slice):
            # Slice of positions - return concatenated
            import numpy as np

            start, stop, step = pos_key.start, pos_key.stop, pos_key.step
            selected_positions = self._positions[start:stop:step]

            # Load all arrays and stack them
            arrays = [
                self._load_array(idx)[key[1:] if len(key) > 1 else ...]
                for idx in selected_positions
            ]
            return np.stack(arrays, axis=0)

        else:
            # Fallback for other key types
            ary = self._load_array(self._positions[0])
            return ary[key[1:] if len(key) > 1 else ...]


def visualize_array(arrays: dict[int, Any]) -> None:
    """Visualize arrays with position slider using ndv.

    Parameters
    ----------
    arrays : dict[int, Any]
        Dictionary mapping position index to array-like object or path string.
    """
    try:
        import ndv

        if len(arrays) == 0:
            print("No arrays to visualize")
            return

        wrapper = PositionDataWrapper(arrays)
        ndv.imshow(wrapper)

    except Exception as e:
        print(f"Could not visualize array: {e}")
        import traceback

        traceback.print_exc()


visualize_array(handler.arrays)
