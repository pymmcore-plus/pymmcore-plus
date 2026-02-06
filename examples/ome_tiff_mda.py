from __future__ import annotations

from useq import MDASequence

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import mda_listeners_connected
from pymmcore_plus.mda.handlers import OMETiffWriter

core = CMMCorePlus.instance()
core.loadSystemConfiguration("tests/local_config.cfg")
core.setPixelSizeConfig("Res40x")

sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 2}],
    stage_positions=[{"x": 1, "y": 1, "name": "some position"}, {"x": 0, "y": 0}],
    time_plan={"interval": 0.66, "loops": 3},
    z_plan={"range": 4, "step": 0.76},
    axis_order="tpcz",
)

with mda_listeners_connected(OMETiffWriter("example.ome.tiff")):
    core.mda.run(sequence)
