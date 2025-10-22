
import time
import useq
from useq import MDASequence

from pymmcore_plus import CMMCorePlus

mmc = CMMCorePlus()

# Without arguments, this will load the demo config
mmc.loadSystemConfiguration()

# sequence = MDASequence(
#     channels=(useq.Channel(config="FITC", exposure=50),),
#     time_plan=useq.TIntervalLoops(interval=5, loops=4),
#     # z_plan=useq.ZAbsolutePositions(absolute=[50]),
#     axis_order=("c", "z", "t"),
#     keep_shutter_open_across=("c", "z", "t"),
# )


# def p(e, t):
#     print(f"Time: {t}")

# mmc.mda.events.awaitingEvent.connect(p)

sequence = MDASequence(
    time_plan={"interval": 0, "loops": 100},
)
mmc.setExposure(50)

acq_thread = mmc.run_mda(sequence)
while acq_thread.is_alive():
    time.sleep(0.5)
    mmc.mda.cancel()
    # mmc.mda.toggle_pause()

