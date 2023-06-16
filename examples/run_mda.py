import numpy as np
from pymmcore_plus import CMMCorePlus
from useq import MDAEvent, MDASequence

# see https://pymmcore-plus.github.io/useq-schema/api/ (1)
sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 50}],
    time_plan={"interval": 2, "loops": 5},
    z_plan={"range": 4, "step": 0.5},
    axis_order="tpcz",
)

mmc = CMMCorePlus.instance()  # (2)!
mmc.loadSystemConfiguration()  #  load demo configuration (3)


# connect callback using a decorator (4)
@mmc.mda.events.frameReady.connect
def new_frame(img: np.ndarray, event: MDAEvent):
    print(img.shape)


# or connect callback using a function
def on_start(sequence: MDASequence):
    print(f"now starting sequence {sequence.uid}!")


mmc.mda.events.sequenceStarted.connect(on_start)

# run the sequence in a separate thread (5)
mmc.run_mda(sequence)
