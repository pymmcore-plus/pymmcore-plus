from __future__ import annotations

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import mda_listeners_connected
from pymmcore_plus.mda.handlers import OMETiffWriter
from useq import MDASequence

core = CMMCorePlus.instance()
core.loadSystemConfiguration("tests/local_config.cfg")
core.setPixelSizeConfig("Res40x")

sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 2}],
    stage_positions=[{"x": 1, "y": 1, "name": "some position"}, {"x": 0, "y": 0}],
    time_plan={"interval": 0.66, "loops": 3},
    z_plan={"range": 4, "step": 0.76},
    axis_order="ptcz",
)

# sequence = MDASequence(
#     channels=["FITC"],
#     stage_positions=[(222, 1, 1), (111, 0, 0)],
#     time_plan={"interval": 0.2, "loops": 5},
#     axis_order="ptc",
# )

writer = OMETiffWriter("example.ome.tiff")

with mda_listeners_connected(writer):
    core.mda.run(sequence)