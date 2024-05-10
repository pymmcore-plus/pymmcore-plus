from __future__ import annotations

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import mda_listeners_connected
from pymmcore_plus.mda.handlers._tensorstore_writer import TensorStoreWriter
from useq import MDASequence

core = CMMCorePlus.instance()
core.loadSystemConfiguration()

sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 1}],
    # stage_positions=[{"x": 1, "y": 1, "name": "some position"}, {"x": 0, "y": 0}],
    time_plan={"interval": 2, "loops": 3},
    z_plan={"range": 4, "step": 0.5},
    axis_order="tpcz",
)

writer = TensorStoreWriter("dataset", overwrite=True)

with mda_listeners_connected(writer):
    core.mda.run(sequence)
