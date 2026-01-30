import useq
import yaozarrs
from ome_types import from_tiff

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.handlers import OMEWriterHandler

# ==================== CONFIGURATION ====================
# Set OPTION to 1, 2, or 3:
#   1 = Manual signal connections (sequenceStarted, frameReady, sequenceFinished)
#   2 = Pass handler object to mmc.mda.run(output=handler)
#   3 = Pass path string to mmc.mda.run(output=path)
OPTION = 1

# Set FORMAT to "zarr" or "tiff"
FORMAT = "zarr"
# FORMAT = "tiff"
# =======================================================


def validate_output(path: str, fmt: str) -> None:
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

# Configure paths and backend based on FORMAT
if FORMAT == "zarr":
    output_path = f"/Users/fdrgsp/Desktop/out/test{OPTION}.ome.zarr"
    backend = "tensorstore"
else:
    output_path = f"/Users/fdrgsp/Desktop/out/test{OPTION}.ome.tiff"
    backend = "tifffile"

# Sequence
seq = useq.MDASequence(
    axis_order="pzc",
    channels=["DAPI", "FITC"],
    z_plan={"range": 2, "step": 0.4},
    # stage_positions=((0, 0), (100, 100)),
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
    handler = OMEWriterHandler(output_path, backend=backend, overwrite=True)
    mmc.mda.events.sequenceStarted.connect(handler.sequenceStarted)
    mmc.mda.events.frameReady.connect(handler.frameReady)
    mmc.mda.events.sequenceFinished.connect(handler.sequenceFinished)
    mmc.mda.run(seq)

elif OPTION == 2:
    # Option 2: Pass handler object to run()
    handler = OMEWriterHandler(output_path, backend=backend, overwrite=True)
    mmc.mda.run(seq, output=handler)

elif OPTION == 3:
    # Option 3: Pass path string to run()
    mmc.mda.run(seq, output=output_path)

# Validate output
validate_output(output_path, FORMAT)
