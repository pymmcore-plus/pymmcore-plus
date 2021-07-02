from useq import MDASequence

from pymmcore_plus import CMMCorePlus

# see https://github.com/tlambert03/useq-schema
sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 50}],
    time_plan={"interval": 2, "loops": 5},
    z_plan={"range": 4, "step": 0.5},
    axis_order="tpcz",
)

mmc = CMMCorePlus()
mmc.loadSystemConfiguration("demo")
mmc.run_mda(sequence)
