from __future__ import annotations

import time
from unittest.mock import Mock

import pytest

from pymmcore_plus import CMMCorePlus
from pymmcore_plus._accumulator import (
    AbstractChangeAccumulator,
    DeviceAccumulator,
    PositionChangeAccumulator,
    XYPositionChangeAccumulator,
)
from pymmcore_plus.core._constants import DeviceType


def _await_batcher(batcher: AbstractChangeAccumulator) -> None:
    """Wait for the batcher to finish."""
    while True:
        if batcher.poll_done():
            break
        time.sleep(0.01)


def test_stage_position_accumulator() -> None:
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    device_obj = core.getDeviceObject(core.getFocusDevice(), DeviceType.Stage)
    accum = device_obj.getPositionAccumulator()
    assert isinstance(accum, PositionChangeAccumulator)

    mock = Mock()
    accum.finished.connect(mock)

    # Test relative moves
    accum.add_relative(10)
    accum.add_relative(20)
    assert accum.target == 30
    _await_batcher(accum)
    mock.assert_called_once()
    assert device_obj.position == 30
    assert not accum.is_moving
    assert accum.poll_done() is False

    # Test absolute moves
    mock.reset_mock()
    accum.add_relative(20)
    accum.set_absolute(10)
    assert accum.target == 10
    _await_batcher(accum)
    mock.assert_called_once()
    assert device_obj.position == 10
    assert accum.target is None


def test_xystage_position_accumulator() -> None:
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    device_obj = core.getDeviceObject(core.getXYStageDevice(), DeviceType.XYStage)
    accum = device_obj.getPositionAccumulator()
    assert isinstance(accum, XYPositionChangeAccumulator)

    mock = Mock()
    accum.finished.connect(mock)

    # Test relative moves
    accum.add_relative([10, 10])
    accum.add_relative([20, 20])
    assert accum.target == [30, 30]
    _await_batcher(accum)
    mock.assert_called_once()
    assert device_obj.position == (30, 30)
    assert not accum.is_moving
    assert accum.poll_done() is False

    # Test absolute moves
    mock.reset_mock()
    accum.add_relative((20, 20))
    accum.set_absolute((10, 10))
    assert accum.target == [10, 10]
    _await_batcher(accum)
    mock.assert_called_once()
    assert [round(x, 2) for x in device_obj.position] == [10, 10]
    assert accum.target is None


def test_invalid_type():
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    obj1 = DeviceAccumulator.get_cached("XY", core)  # type: ignore
    assert isinstance(obj1, XYPositionChangeAccumulator)
    assert XYPositionChangeAccumulator.get_cached("XY", core) is obj1

    with pytest.raises(
        TypeError, match="Cannot create PositionChangeAccumulator for 'XY'"
    ):
        PositionChangeAccumulator.get_cached("XY", core)

    with pytest.raises(ValueError, match="No matching DeviceTypeMixin subclass found"):
        DeviceAccumulator.get_cached("Camera", core)

    core2 = CMMCorePlus()
    core2.loadSystemConfiguration()
    obj2 = DeviceAccumulator.get_cached("XY", core2)  # type: ignore
    assert isinstance(obj2, XYPositionChangeAccumulator)
    assert obj1 is not obj2
