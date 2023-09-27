from __future__ import annotations

from useq import MDASequence, Position

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import mda_listeners_connected
from pymmcore_plus.mda.handlers import TiffSequenceWriter

core = CMMCorePlus.instance()
core.loadSystemConfiguration()

sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 1}],
    stage_positions=[
        {"x": 1, "y": 1, "name": "some position"},
        Position(
            x=2, y=2, z=3, sequence=MDASequence(grid_plan={"rows": 2, "columns": 2})
        ),
    ],
    time_plan={"interval": 2, "loops": 2},
    z_plan={"range": 2, "step": 0.5},
    axis_order="tpcz",
)

writer = TiffSequenceWriter(
    "data_folder",
    overwrite=True,
    prefix="test",
    include_frame_count=True,
)

with mda_listeners_connected(writer):
    core.mda.run(sequence)
