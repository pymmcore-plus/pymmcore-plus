from pymmcore_plus import FocusDirection
from pymmcore_plus.experimental.unicore import StageDevice, UniMMCore


class MyZStage(StageDevice):
    """Example of a Z Stage device"""

    def __init__(self):
        super().__init__()
        self.position = 0.0
        self.previous_position = 0.0
        self.origin = 0.0
        self.direction = 0.0

    def home(self) -> None:
        self.HOME = True

    def stop(self) -> None:
        self.STOP = True

    def set_origin(self) -> None:
        self.previous_position = self.position
        self.origin = self.position

    def set_position_um(self, val: float) -> None:
        self.previous_position = self.position
        self.position = val
        self.direction = self._calculate_direction()

    def get_position_um(self) -> float:
        return self.position

    def get_focus_direction(self) -> FocusDirection:
        """Translate the movement of the z stage"""
        if self.direction > 0.0:
            return FocusDirection.FocusDirectionTowardSample
        else:
            return FocusDirection.FocusDirectionAwayFromSample

    def set_focus_direction(self, sign: int) -> None:
        """Set the focus direction of the stage
        if sign > 0.0 direction towards sample
        if sign < 0.0 direction away from sample
        """
        if sign > 0.0:
            self.direction = FocusDirection.FocusDirectionTowardSample
        if sign < 0.0:
            self.direction = FocusDirection.FocusDirectionAwayFromSample

    def _calculate_direction(self) -> float:
        return self.position - self.previous_position


def test_unicore_z_stage():
    core = UniMMCore()

    stage = MyZStage()

    # load z stage
    core.loadPyDevice("ZStage", stage)
    core.initializeDevice("ZStage")

    # set the focus device
    core.setFocusDevice("ZStage")

    assert core.getFocusDevice() == "ZStage"
    assert core.getZPosition() == 0.0

    # set new position
    core.setZPosition(20.0)
    assert core.getZPosition() == 20.0

    # test focus direction
    core.home("ZStage")
    assert stage.HOME
    core.stop("ZStage")
    assert stage.STOP

    # test origin
    core.setZPosition(20.0)
    assert core.getZPosition() == 20.0
    core.setOrigin()
    core.setZPosition(10.0)
    assert core.getZPosition() == 10.0
    assert stage.previous_position == 20.0
    assert stage.origin == 20.0
