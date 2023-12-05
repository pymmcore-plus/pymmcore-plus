from pymmcore_plus import CMMCorePlus
import time


mmc = CMMCorePlus()
mmc.loadSystemConfiguration()

class Receiver:
    def __init__(self, mmc: CMMCorePlus):
        self._value = None
        self.mmc = mmc
        self.mmc.events.XYStagePositionChanged.connect(self._on_stage_position_changed)

    def _on_stage_position_changed(self):
        print("Signal received")


receiver = Receiver(mmc)

mmc.setXYPosition(0, 0)
time.sleep(2)
mmc.setXYPosition(1, 1)
