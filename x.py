import time

from useq import MDASequence

from pymmcore_plus.mocks import mock_sequenceable_core

mmc = mock_sequenceable_core()
assert mmc.mda.engine.mmcore is mmc
assert mmc.mda.engine._mmc is mmc
# cfg_path = r"path\to\config.cfg"
# mmc.loadSystemConfiguration()

# mmc.setConfig("Channel", "DAPI")

# print("Running first live acquisition")
# # First test that things are ok
# mmc.startContinuousSequenceAcquisition(100)
# # pause execution for 15s

# time.sleep(1)
# mmc.stopSequenceAcquisition()

# Now generate and then run mda acquisition
sequence = MDASequence(
    channels=[
        {"config": "DAPI", "exposure": 50},
        {"config": "FITC", "exposure": 50},
    ],
    time_plan={"interval": 0, "loops": 50},
    axis_order="ct",
    keep_shutter_open_across=("t",),
)


print("Running sequenced MDA")
acquisition = mmc.mda.run(sequence)


print("Running second live acquisition")
# Now test again continuous sequence acquisition
mmc.setConfig("Channel", "DAPI")

# First test that things are ok
mmc.startContinuousSequenceAcquisition(10)

# pause execution for 15s
time.sleep(1)
mmc.stopSequenceAcquisition()

print(mmc.snapImage.call_count)
