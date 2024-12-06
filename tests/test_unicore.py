from typing import ClassVar

from pymmcore_plus.core._constants import (
    DeviceInitializationState,
    DeviceType,
    PropertyType,
)
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

    PYDEV = "pyXY"
    core.load_py_device(PYDEV, stage)
    assert PYDEV in core.getLoadedDevices()
    assert core.getDeviceLibrary(PYDEV) == __name__  # because it's in this module
    assert core.getDeviceName(PYDEV) == MyStage.__name__
    assert core.getDeviceType(PYDEV) == DeviceType.XYStage
    assert core.getDeviceDescription(PYDEV) == "Example XY stage device."  # docstring

    assert (
        core.getDeviceInitializationState(PYDEV)
        is DeviceInitializationState.Uninitialized
    )
    core.initializeDevice(PYDEV)
    assert (
        core.getDeviceInitializationState(PYDEV)
        is DeviceInitializationState.InitializedSuccessfully
    )

    # PROPERTIES

    PROP_NAME = "propA"
    assert PROP_NAME in core.getDevicePropertyNames(PYDEV)
    assert core.hasProperty(PYDEV, PROP_NAME)
    assert core.isPropertyPreInit(PYDEV, PROP_NAME) is False
    assert core.isPropertyReadOnly(PYDEV, PROP_NAME) is False
    assert core.hasPropertyLimits(PYDEV, PROP_NAME)
    assert core.getPropertyLowerLimit(PYDEV, PROP_NAME) == 0.0
    assert core.getPropertyUpperLimit(PYDEV, PROP_NAME) == 100.0
    assert core.getPropertyType(PYDEV, PROP_NAME) == PropertyType.Float
    assert core.getProperty(PYDEV, PROP_NAME) == 1.0
    assert core.getPropertyFromCache(PYDEV, PROP_NAME) == 1.0

    assert not core.deviceBusy(PYDEV)
    core.waitForDevice(PYDEV)

    # METHODS

    # set the core XY stage device to the python device, dropping the C-side device
    core.setXYStageDevice(PYDEV)
    assert core.getXYStageDevice() == PYDEV
    NEW_POS = (10, 20)
    core.setXYPosition(*NEW_POS)
    assert core.getXYPosition() == NEW_POS

    # can still set and query the C-side device directly
    core.waitForDevice("XY")
    core.setXYPosition("XY", 1.5, 3.7)
    x, y = core.getXYPosition("XY")
    assert (round(x, 1), round(y, 1)) == (1.5, 3.7)
    assert core.getXYPosition(PYDEV) == NEW_POS

    core.setOriginXY(PYDEV)
    assert core.getXYPosition(PYDEV) == (0, 0)
    assert tuple(stage.ORIGIN) == NEW_POS

    core.setRelativeXYPosition(PYDEV, 1, 2)
    assert core.getXYPosition(PYDEV) == (1, 2)

    core.home(PYDEV)
    core.stop(PYDEV)
    assert stage.HOMED
    assert stage.STOPPED
