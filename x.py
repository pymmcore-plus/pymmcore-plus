# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pymmcore-plus",
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
    uv run x.py [FORMAT] [OPTION]

Arguments:
    FORMAT: Output format (default: zarr)
        - zarr: Write to OME-Zarr using tensorstore backend
        - tiff: Write to OME-TIFF using tifffile backend
        - zarr-memory: Write to temporary in-memory zarr store
        - tiff-sequence: Write to image sequence directory

    OPTION: Handler integration method (default: 1)
        - 1: Manual signal connections (sequenceStarted, frameReady, sequenceFinished)
        - 2: Pass handler object to mmc.mda.run(output=handler)
        - 3: Pass Output object to mmc.mda.run(output=Output(path, format))
        - 4: Pass path string to mmc.mda.run(output=path)

Examples
--------
    uv run x.py zarr 1
    uv run x.py zarr-memory 2
    uv run x.py tiff 3
    uv run x.py zarr 4
"""

import sys
from pathlib import Path

import useq
import yaozarrs
from ome_types import from_tiff

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import Output
from pymmcore_plus.mda.handlers import OMEWriterHandler
from pymmcore_plus.mda.handlers._img_sequence_writer import ImageSequenceWriter

# ==================== CONFIGURATION ====================
# Set FORMAT from command line argument or default
FORMAT = sys.argv[1] if len(sys.argv) > 1 else "zarr"
# Valid options: "zarr", "tiff", "zarr-memory", "tiff-sequence"

# Set OPTION from command line argument or default
# OPTION determines how to pass the handler to mda.run():
#   1 = Manual signal connections (sequenceStarted, frameReady, sequenceFinished)
#   2 = Pass handler object to mmc.mda.run(output=handler)
#   3 = Pass Output object to mmc.mda.run(output=Output(path, format))
#   4 = Pass path string to mmc.mda.run(output=path)
#   5 = Pass list of Output objects to mmc.mda.run(output=[Output1, Output2])
OPTION = int(sys.argv[2]) if len(sys.argv) > 2 else 1

# Output directory on desktop
OUTPUT_DIR = Path.home() / "Desktop" / "pymmcore_writers_examples"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
# =======================================================


def validate_output(path: str, fmt: str) -> None:
    """Validate the output file or directory."""
    if fmt == "zarr":
        yaozarrs.validate_zarr_store(path)
        print("✓ Zarr store is valid")
    elif fmt == "tiff":
        files = [f"{path[:-9]}_p{pos:03d}.ome.tiff" for pos in range(2)]
        for idx, file in enumerate(files):
            from_tiff(file)
            print(f"✓ TIFF file {idx} is valid")


# Setup core
mmc = CMMCorePlus.instance()
mmc.loadSystemConfiguration("/Users/fdrgsp/Desktop/test_config.cfg")
mmc.setProperty("Objective", "Label", "Nikon 20X Plan Fluor ELWD")

# Configure Output based on FORMAT
if FORMAT == "zarr":
    out = Output(f"{OUTPUT_DIR}/test{OPTION}.ome.zarr", format="tensorstore")
elif FORMAT == "tiff":
    out = Output(f"{OUTPUT_DIR}/test{OPTION}.ome.tiff", format="tifffile")
elif FORMAT == "zarr-memory":
    out = Output("memory://", format="tensorstore")
elif FORMAT == "tiff-sequence":
    # No format needed for ImageSequenceWriter
    out = Output(f"{OUTPUT_DIR}/test{OPTION}_sequence")
else:
    raise ValueError(f"Unknown FORMAT: {FORMAT}")

# Sequence
seq = useq.MDASequence(
    axis_order="pzc",
    channels=["DAPI", "FITC"],
    z_plan={"range": 2, "step": 1.0},
    stage_positions=useq.WellPlatePlan(
        plate=useq.WellPlate.from_str("96-well"),
        a1_center_xy=(0, 0),
        selected_wells=((0, 1), (0, 1)),
        well_points_plan=useq.GridRowsColumns(rows=2, columns=2),
    ),
)

# Run based on OPTION
if OPTION == 1:
    # Option 1: Manual signal connections
    if FORMAT == "tiff-sequence":
        handler = ImageSequenceWriter(out.path, overwrite=True)
    else:
        handler = OMEWriterHandler(out.path, backend=out.format, overwrite=True)

    mmc.mda.events.sequenceStarted.connect(handler.sequenceStarted)
    mmc.mda.events.frameReady.connect(handler.frameReady)
    mmc.mda.events.sequenceFinished.connect(handler.sequenceFinished)
    mmc.mda.run(seq)

elif OPTION == 2:
    # Option 2: Pass handler object directly to output
    if FORMAT == "tiff-sequence":
        handler = ImageSequenceWriter(out.path, overwrite=True)
    else:
        handler = OMEWriterHandler(out.path, backend=out.format, overwrite=True)

    mmc.mda.run(seq, output=handler)

elif OPTION == 3:
    # Option 3: Pass Output object to output
    mmc.mda.run(seq, output=out)

elif OPTION == 4:
    # Option 4: Pass path string to output
    mmc.mda.run(seq, output=out.path)

elif OPTION == 5:
    # Option 5: Pass list of Output objects
    if FORMAT == "tiff-sequence":
        mmc.mda.run(seq, output=[out.path, f"{out.path}_1"])
    else:
        path_str = str(out.path)
        if out.format == "tifffile":
            out1 = path_str.replace(".ome.tiff", "_1.ome.tiff")
        else:
            out1 = path_str.replace(".ome.zarr", "_1.ome.zarr")
        mmc.mda.run(
            seq,
            output=[out, Output(out1, format=out.format)],
        )

# Validate output
validate_output(str(out.path), FORMAT)
