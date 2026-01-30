"""Example of using ome_writers to store data acquired with pymmcore-plus."""

import sys

import numpy as np
import useq
from ome_writers import AcquisitionSettings, create_stream, dims_from_useq

from pymmcore_plus import CMMCorePlus

# Initialize pymmcore-plus core and load system configuration (null = demo config)
core = CMMCorePlus()
core.loadSystemConfiguration()

# Create a MDASequence, which will be used to run the MDA with pymmcore-plus
seq = useq.MDASequence(
    axis_order="ptcz",
    # stage_positions=[(0.0, 0.0), (10.0, 10.0)],
    stage_positions=useq.WellPlatePlan(
        plate=useq.WellPlate.from_str("96-well"),
        a1_center_xy=(0, 0),
        selected_wells=((0, 1), (0, 1)),
        well_points_plan=useq.GridRowsColumns(rows=2, columns=2),
    ),
    time_plan={"interval": 0.1, "loops": 3},
    channels=["DAPI", "Cy5"],
    z_plan={"range": 2, "step": 1.0},
)

# Setup the AcquisitionSettings, converting the MDASequence to ome-writers Dimensions
# Derive backend from command line argument (default: auto)
BACKEND = "auto" if len(sys.argv) < 2 else sys.argv[1]
suffix = ".ome.tiff" if BACKEND == "tifffile" else ".ome.zarr"

settings = AcquisitionSettings(
    root_path=f"example_pymmcore_plus{suffix}",
    # use dims_from_useq to convert MDASequence to ome_writers.Dimensions
    dimensions=dims_from_useq(
        seq,
        image_width=core.getImageWidth(),
        image_height=core.getImageHeight(),
        pixel_size_um=core.getPixelSizeUm(),
    ),
    dtype=f"uint{core.getImageBitDepth()}",
    overwrite=True,
    backend=BACKEND,
)

# Open the stream and run the sequence
with create_stream(settings) as stream:
    # Connect frameReady event to append frames to the stream
    @core.mda.events.frameReady.connect
    def _on_frame(frame: np.ndarray, event: useq.MDAEvent, metadata: dict) -> None:
        stream.append(frame)

    # Tell pymmcore-plus to run the useq.MDASequence
    core.mda.run(seq)


if settings.format == "zarr":
    import yaozarrs

    yaozarrs.validate_zarr_store(settings.root_path)
    print("✓ Zarr store is valid")

if settings.format == "tiff":
    from ome_types import from_tiff

    if len(seq.stage_positions) == 0:
        files = [settings.root_path]
    else:
        files = [f"{settings.root_path[:-9]}_p{pos:03d}.ome.tiff" for pos in range(2)]
    for idx, file in enumerate(files):
        from_tiff(file)
        print(f"✓ TIFF file {idx} is valid")
