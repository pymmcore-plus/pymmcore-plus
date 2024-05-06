from __future__ import annotations

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import mda_listeners_connected
from pymmcore_plus.mda.handlers import SOMEZarrWriter
from useq import MDASequence

core = CMMCorePlus.instance()
core.loadSystemConfiguration()

sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 1}],
    # stage_positions=[{"x": 1, "y": 1, "name": "some position"}, {"x": 0, "y": 0}],
    time_plan={"interval": 2, "loops": 2},
    z_plan={"range": 4, "step": 0.5},
    axis_order="tpcz",
)

# use SOMEZarrHandler("file.zarr") to write to a directory
# use SOMEZarrHandler.in_tmpdir() to write to a temporary directory
# pass None or no arguments to write to Memory
writer = SOMEZarrWriter("example.zarr", overwrite=True, minify_attrs_metadata=True)

with mda_listeners_connected(writer):
    core.mda.run(sequence)
