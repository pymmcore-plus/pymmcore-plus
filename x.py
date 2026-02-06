# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pymmcore-plus[io]",
#     "useq-schema",
#     "yaozarrs",
#     "ome-types",
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

Examples
--------
    uv run x.py tensorstore 1              # Single tensorstore output
    uv run x.py tifffile 2                 # Single tifffile output
    uv run x.py tensorstore tifffile 3     # Both tensorstore and tifffile
    uv run x.py tensorstore zarr_python tifffile 4  # Three outputs
"""

import sys
from datetime import datetime
from pathlib import Path

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

# Validate outputs
validation_paths = []
validation_formats = []

outputs_list = outputs if isinstance(outputs, list) else [outputs]
for idx, out in enumerate(outputs_list):
    validation_paths.append(str(out.path))
    # Use the backend from BACKENDS list to determine format
    backend = BACKENDS[idx] if idx < len(BACKENDS) else BACKENDS[0]
    validation_formats.append(backend)

validate_output(validation_paths, validation_formats)
