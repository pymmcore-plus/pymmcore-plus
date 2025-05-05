from __future__ import annotations

import time
from contextlib import suppress
from typing import Any
from unittest.mock import Mock

import pytest

from pymmcore_plus import CMMCorePlus
from pymmcore_plus._accumulator import (
    AbstractChangeAccumulator,
    PositionAccumulator,
    XYPositionAccumulator,
)


def _await_batcher(batcher: AbstractChangeAccumulator) -> None:
    """Wait for the batcher to finish."""
    while True:
        if batcher.poll_done():
            break
        time.sleep(0.01)


@pytest.mark.parametrize("device", ["XY", "Z"])
def test_stage_batcher(device: str) -> None:
    """Test the StageBatcher class."""
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    with suppress(RuntimeError):
        core.setProperty(device, "Velocity", 1)
    batcher = core.getChangeAccumulator(device)
    if device == "XY":
        assert isinstance(batcher, XYPositionAccumulator)
    else:
        assert isinstance(batcher, PositionAccumulator)
    mock = Mock()
    batcher.finished.connect(mock)

    # Test relative moves
    moves: Any = [(10, 10), (20, 20)] if device == "XY" else [10, 20]
    target = [30, 30] if device == "XY" else 30
    for move in moves:
        batcher.add_relative(move)
    assert batcher.target == target
    _await_batcher(batcher)
    mock.assert_called_once()
    assert type(target)(batcher._get_value()) == target  # type: ignore
    assert not batcher.is_moving
    assert batcher.poll_done() is False

    # Test absolute moves
    mock.reset_mock()
    batcher.add_relative((20, 20) if device == "XY" else 20)  # type: ignore
    batcher.set_absolute((10, 10) if device == "XY" else 10)  # type: ignore
    target = [10, 10] if device == "XY" else 10
    assert batcher.target == target

    _await_batcher(batcher)
    mock.assert_called_once()
    val = type(target)(batcher._get_value())  # type: ignore
    if device == "XY":
        assert [round(x, 2) for x in val] == target  # type: ignore
    else:
        assert round(val, 2) == target  # type: ignore
    assert batcher.target is None
