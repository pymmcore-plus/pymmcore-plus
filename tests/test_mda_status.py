"""Tests for MDA runner cancel/pause during hardware sequences."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
import useq

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


@pytest.mark.parametrize("hardware_seq", [True, False])
def test_pause_and_cancel_mid_sequence(
    core: CMMCorePlus, caplog: pytest.LogCaptureFixture, hardware_seq: bool
) -> None:
    """Pause then cancel mid-sequence stops acquisition early."""
    core.mda.engine.use_hardware_sequencing = hardware_seq

    frame_count = 0

    cancel_mock = Mock()
    core.mda.events.sequenceCanceled.connect(cancel_mock)

    @core.mda.events.frameReady.connect
    def _on_frame() -> None:
        nonlocal frame_count
        frame_count += 1
        if frame_count == 1 and hardware_seq:
            core.mda.toggle_pause()
        elif frame_count == 3:
            core.mda.cancel()

    sequence = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=50))

    with caplog.at_level(logging.WARNING, logger="pymmcore-plus"):
        core.mda.run(sequence)

    assert frame_count < 50
    assert any("MDA Canceled:" in r.message for r in caplog.records)
    cancel_mock.assert_called_once()
    # hardware sequences can't truly pause, only warn
    if hardware_seq:
        assert any("cannot be yet paused" in r.message for r in caplog.records)
