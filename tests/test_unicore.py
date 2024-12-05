from typing import ClassVar

from pymmcore_plus.core._constants import DeviceInitializationState, PropertyType
from pymmcore_plus.unicore import UniMMCore
from pymmcore_plus.unicore._properties import pymm_property
from pymmcore_plus.unicore._xy_stage_device import XYStageDevice


class MyStage(XYStageDevice):
    """Example XY stage device."""

    STOPPED = False
    HOMED = False
    ORIGIN: ClassVar[list[float]] = [0.0, 0.0]
    _pos: ClassVar[list[float]] = [0.0, 0.0]

    @pymm_property(limits=(0.0, 100.0))
    def propA(self) -> float:
        """Some property."""
        return 1

    def set_position_um(self, x: float, y: float) -> None:
        """Set the position of the stage."""
        self._pos[:] = [x, y]

    def get_position_um(self) -> tuple[float, float]:
        """Get the current position of the stage."""
        return tuple(self._pos)  # type: ignore

    def set_origin_x(self) -> None:
        self._pos[0], self.ORIGIN[0] = 0.0, self._pos[0]

    def set_origin_y(self) -> None:
        self._pos[1], self.ORIGIN[1] = 0.0, self._pos[1]

    def stop(self) -> None:
        self.STOPPED = True

    def home(self) -> None:
        self.HOMED = True


def test_unicore():
    core = UniMMCore()
    core.loadSystemConfiguration()
    # print status of C-side XY stage device
    assert core.getXYStageDevice() == "XY"
    core.setXYPosition(100, 200)
    x, y = core.getXYPosition()
    assert (round(x), round(y)) == (100, 200)

    # load a python XY stage device
    stage = MyStage()
    core.load_py_device("pyXY", stage)
    assert "pyXY" in core.getLoadedDevices()

    assert (
        core.getDeviceInitializationState("pyXY")
        is DeviceInitializationState.Uninitialized
    )
    core.initializeDevice("pyXY")
    assert (
        core.getDeviceInitializationState("pyXY")
        is DeviceInitializationState.InitializedSuccessfully
    )
    PROP_NAME = "propA"
    assert PROP_NAME in core.getDevicePropertyNames("pyXY")
    assert core.hasProperty("pyXY", PROP_NAME)
    assert core.isPropertyPreInit("pyXY", PROP_NAME) is False
    assert core.isPropertyReadOnly("pyXY", PROP_NAME) is False
    assert core.hasPropertyLimits("pyXY", PROP_NAME)
    assert core.getPropertyLowerLimit("pyXY", PROP_NAME) == 0.0
    assert core.getPropertyUpperLimit("pyXY", PROP_NAME) == 100.0
    assert core.getPropertyType("pyXY", PROP_NAME) == PropertyType.Float
    assert core.getProperty("pyXY", PROP_NAME) == 1.0
    assert core.getPropertyFromCache("pyXY", PROP_NAME) == 1.0

    # set the core XY stage device to the python device, dropping the C-side device
    core.setXYStageDevice("pyXY")
    assert core.getXYStageDevice() == "pyXY"
    NEW_POS = (10, 20)
    core.setXYPosition(*NEW_POS)
    assert core.getXYPosition() == NEW_POS

    # can still set and query the C-side device directly
    core.waitForDevice("XY")
    core.setXYPosition("XY", 1.5, 3.7)
    x, y = core.getXYPosition("XY")
    assert (round(x, 1), round(y, 1)) == (1.5, 3.7)
    assert core.getXYPosition("pyXY") == NEW_POS

    core.setOriginXY("pyXY")
    assert core.getXYPosition("pyXY") == (0, 0)
    assert tuple(stage.ORIGIN) == NEW_POS

    core.setRelativeXYPosition("pyXY", 1, 2)
    assert core.getXYPosition("pyXY") == (1, 2)

    core.home("pyXY")
    core.stop("pyXY")
    assert stage.HOMED
    assert stage.STOPPED
