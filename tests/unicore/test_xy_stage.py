from pymmcore_plus.core._constants import Keyword
from pymmcore_plus.experimental.unicore import (
    UniMMCore,
    XYStageDevice,
    XYStepperStageDevice,
)

XYDEV = "pyXY"


class MyStage(XYStageDevice):
    """Example XY stage device."""

    def __init__(self) -> None:
        super().__init__()
        self.origin: tuple[float, float] = (0.0, 0.0)
        self.position: tuple[float, float] = (0.0, 0.0)

    def set_position_um(self, x: float, y: float) -> None:
        """Set the position of the stage."""
        self.position = (x, y)

    def get_position_um(self) -> tuple[float, float]:
        """Get the current position of the stage."""
        return tuple(self.position)  # type: ignore

    def set_origin_x(self) -> None:
        px, py = self.position
        self.origin = (px, self.origin[1])
        self.position = (0, py)

    def set_origin_y(self) -> None:
        px, py = self.position
        self.origin = (self.origin[0], py)
        self.position = (px, 0)

    def stop(self) -> None:
        self.STOPPED = True

    def home(self) -> None:
        self.HOMED = True


def test_unicore_xy_stage():
    core = UniMMCore()
    core.loadSystemConfiguration()

    # print status of C-side XY stage device
    assert core.getXYStageDevice() == "XY"
    core.setXYPosition(100, 200)
    x, y = core.getXYPosition()
    assert (round(x), round(y)) == (100, 200)

    # load a python XY stage device
    stage = MyStage()

    core.load_py_device(XYDEV, stage)
    core.initializeDevice(XYDEV)

    # set the core XY stage device to the python device, dropping the C-side device
    core.setXYStageDevice(XYDEV)
    assert core.getXYStageDevice() == XYDEV
    NEW_POS = (10, 20)
    core.setXYPosition(*NEW_POS)
    assert core.getXYPosition() == NEW_POS

    # can still set and query the C-side device directly
    core.waitForDevice("XY")
    core.setXYPosition("XY", 1.5, 3.7)
    x, y = core.getXYPosition("XY")
    assert (round(x, 1), round(y, 1)) == (1.5, 3.7)
    assert core.getXYPosition(XYDEV) == NEW_POS

    # test stage methods
    core.setOriginXY(XYDEV)
    assert core.getXYPosition(XYDEV) == (0, 0)
    assert tuple(stage.origin) == NEW_POS

    core.setRelativeXYPosition(XYDEV, 1, 2)
    assert core.getXYPosition(XYDEV) == (1, 2)

    core.home(XYDEV)
    core.stop(XYDEV)
    assert stage.HOMED
    assert stage.STOPPED

    core.setXYStageDevice("")
    assert core._pycore.current(Keyword.CoreXYStage) is None


class MyStepperStage(XYStepperStageDevice):
    def __init__(self) -> None:
        super().__init__()
        self.position_steps: tuple[int, int] = (0, 0)

    def get_position_steps(self) -> tuple[int, int]:
        return self.position_steps

    def set_position_steps(self, x: int, y: int) -> None:
        self.position_steps = (x, y)

    def get_step_size_x_um(self) -> float:
        return 0.1

    def get_step_size_y_um(self) -> float:
        return 0.1

    def stop(self) -> None:
        self.STOPPED = True

    def home(self) -> None:
        self.HOMED = True


def test_unicore_xy_stepper_stage():
    core = UniMMCore()

    # load a python XY stage device
    stage = MyStepperStage()

    core.load_py_device(XYDEV, stage)
    core.initializeDevice(XYDEV)
    core.setXYStageDevice(XYDEV)

    # test position
    core.setXYPosition(100.5, 200.5)
    assert stage.position_steps == (1005, 2005)
    assert core.getXYPosition() == (100.5, 200.5)

    core.setProperty(XYDEV, Keyword.Transpose_MirrorX, True)
    core.setProperty(XYDEV, Keyword.Transpose_MirrorY, True)

    assert core.getXYPosition() == (-100.5, -200.5)
    core.setXYPosition(105.5, 205.5)
    assert stage.position_steps == (-1055, -2055)
    assert core.getXYPosition() == (105.5, 205.5)

    core.setRelativeXYPosition(1.5, 2.5)
    assert core.getXYPosition() == (107.0, 208.0)
    steps = stage.position_steps
    assert steps == (-1070, -2080)

    core.setOriginXY()
    assert core.getXYPosition() == (0, 0)
    assert (stage._origin_x_steps, stage._origin_y_steps) == steps

    core.setAdapterOriginXY(500, 600)
    assert core.getXYPosition() == (500, 600)
