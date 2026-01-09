from __future__ import annotations

from useq import MDASequence

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.handlers import OMEWriterHandler

core = CMMCorePlus.instance()
core.loadSystemConfiguration()

sequence = MDASequence(
    axis_order="tpcz",
    channels=["DAPI", {"config": "FITC", "exposure": 1}],
    stage_positions=[(0, 0), (1, 1)],
    time_plan={"interval": 1, "loops": 2},
    z_plan={"range": 4, "step": 0.5},
)

# Set the wanted backend for to write either OME-Zarr:
# ome-zarr: "tensorstore", "acquire-zarr", or "zarr"
writer = OMEWriterHandler(path="example_ts.zarr", backend="tensorstore", overwrite=True)

# or OME-TIFF: "tiff"
# writer = OMEWriterHandler(path="example.ome.tif", backend="tiff", overwrite=True)

core.mda.run(sequence, output=writer)
