import itertools
import sys

import numpy as np
from useq import MDAEvent, MDASequence

from pymmcore_plus import CMMCorePlus

# see https://pymmcore-plus.github.io/useq-schema/api/ (1)
sequence = MDASequence(
    channels=[{"config": "DAPI", "exposure": 10}, {"config": "FITC", "exposure": 50}],
    time_plan={"interval": 1, "loops": 5},
    z_plan={"range": 4, "step": 0.5},
    axis_order="tpcz",
)

mmc = CMMCorePlus.instance()  # (2)!
mmc.loadSystemConfiguration()  #  load demo configuration (3)
counter = itertools.count(1)


# connect callback using a decorator (4)
@mmc.mda.events.frameReady.connect
def new_frame(img: np.ndarray, event: MDAEvent):
    print(f"Frame {next(counter):>3}, shape", img.shape, event.index)


# or connect callback using a function
def on_start(sequence: MDASequence):
    print(f"now starting sequence {sequence.uid}!")


mmc.mda.events.sequenceStarted.connect(on_start)

# parse command line arguments to determine output format, default is no output.
output = None
if "--tiff" in sys.argv:
    output = "example_mda.ome.tiff"
elif "--zarr" in sys.argv:
    output = "example_mda.ome.zarr"

# run the sequence (5)
mmc.mda.run(sequence, output=output, overwrite=True)
