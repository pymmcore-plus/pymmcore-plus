"""Tests for MDA runner pause/cancel during hardware sequences."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import pytest
from useq import MDASequence

from pymmcore_plus._logger import logger

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

    from pymmcore_plus import CMMCorePlus

try:
    import pytestqt
except ImportError:
    pytestqt = None

SKIP_NO_PYTESTQT = pytest.mark.skipif(
    pytestqt is None, reason="pytest-qt not installed"
)


@SKIP_NO_PYTESTQT
@pytest.mark.parametrize("hardware_seq", [True, False])
def test_sequenced_event_paused_and_cancelled(
    core: CMMCorePlus, qtbot: QtBot, hardware_seq: bool
) -> None:
    """Test pausing and then canceling during a hardware-triggered sequence.

    It checks that the sequence is actually cancelled and that the appropriate
    warnings are logged.
    """
    core.mda.engine.use_hardware_sequencing = hardware_seq

    # Temporarily set logger level to WARNING to capture warnings
    original_level = logger.level
    logger.setLevel(logging.WARNING)

    warnings_captured = []

    class WarningHandler(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.WARNING:
                warnings_captured.append(record.getMessage())

    handler = WarningHandler()
    logger.addHandler(handler)

    try:

        def _on_finished(seq):
            t1 = time.perf_counter()
            assert core.mda.is_canceled()
            assert t1 - t0 < 4.5, "Acquisition not canceled!"
            # assert that both pause warning and cancel warning were logged
            if hardware_seq:
                assert len(warnings_captured) == 2
                assert warnings_captured[0] == (
                    "MDA: Pause has been requested, but sequenced acquisition "
                    "cannot be yet paused, only canceled."
                )
                assert "MDA Canceled:" in warnings_captured[1]
            else:
                assert len(warnings_captured) == 1
                assert "MDA Canceled:" in warnings_captured[0]

        core.mda.events.sequenceFinished.connect(_on_finished)

        # With 100 frames at 50ms exposure, full run would take ~5 seconds
        sequence = MDASequence(time_plan={"interval": 0, "loops": 100})
        core.setExposure(50)

        t0 = time.perf_counter()
        with qtbot.waitSignals(
            (
                core.mda.events.sequenceFinished,
                core.mda.events.sequencePauseToggled,
                core.mda.events.sequenceCanceled,
            ),
            timeout=10000,
        ):
            acq_thread = core.run_mda(sequence)
            assert core.mda.is_running()
            paused = False
            while acq_thread.is_alive():
                if not paused:
                    paused = True
                    time.sleep(0.2)
                    core.mda.toggle_pause()
                    assert core.mda.is_pause_requested()
                    assert core.mda.is_running()
                    time.sleep(0.2)
                    if not hardware_seq:
                        assert core.mda.is_paused()
                    # to stop the sequence faster
                    core.mda.cancel()
                    assert not core.mda.is_running()
                    assert not core.mda.is_pause_requested()
                    assert not core.mda.is_paused()
                    assert core.mda.is_cancel_requested()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)
