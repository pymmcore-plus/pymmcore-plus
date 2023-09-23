from __future__ import annotations

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import mda_listeners_connected
from pymmcore_plus.mda.handlers import SimpleTiffWriter
from useq import MDASequence

core = CMMCorePlus.instance()
core.loadSystemConfiguration()

sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 1}],
    stage_positions=[{"x": 1, "y": 1, "name": "some position"}, {"x": 0, "y": 0}],
    time_plan={"interval": 2, "loops": 2},
    z_plan={"range": 4, "step": 0.5},
    axis_order="tpcz",
)

writer = SimpleTiffWriter(
    "data_folder", overwrite=True, prefix="asdf", include_frame_count=True
)

with mda_listeners_connected(writer):
    core.mda.run(sequence)
