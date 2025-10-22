"""Tests for MDA runner status management."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import pytest
from useq import MDASequence

from pymmcore_plus._logger import logger
from pymmcore_plus.mda.events import RunStatus

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


def test_initial_status(core: CMMCorePlus) -> None:
    """Test that the initial status is IDLE."""
    assert core.mda.status == RunStatus.IDLE
    assert not core.mda.is_running()
    assert not core.mda.is_paused()


@SKIP_NO_PYTESTQT
def test_status_during_run(core: CMMCorePlus, qtbot: QtBot) -> None:
    """Test status transitions during a normal MDA run."""
    sequence = MDASequence(time_plan={"interval": 0.3, "loops": 5})

    # Track status changes
    status_changes: list[RunStatus] = []

    def _track_status():
        status_changes.append(core.mda.status)

    def _on_finished(seq):
        assert set(status_changes) == {
            RunStatus.PAUSED_TOGGLED,
            RunStatus.RUNNING,
            RunStatus.COMPLETED,
        }
        assert not core.mda.is_running()
        assert not core.mda.is_paused()
        assert not core.mda.is_canceled()

    # Connect to signals to track status
    core.mda.events.sequenceStarted.connect(_track_status)
    core.mda.events.eventStarted.connect(lambda _: _track_status())
    core.mda.events.awaitingEvent.connect(lambda _: _track_status())
    core.mda.events.frameReady.connect(lambda _: _track_status())
    core.mda.events.sequenceFinished.connect(lambda _: _track_status())
    core.mda.events.sequenceFinished.connect(_on_finished)

    # Check initial state
    assert core.mda.status == RunStatus.IDLE

    # Run the sequence
    with qtbot.waitSignal(core.mda.events.sequenceFinished, timeout=10000):
        acq_thread = core.run_mda(sequence)
        assert core.mda.is_running()
        paused = False
        while acq_thread.is_alive():
            if not paused:
                paused = True
                time.sleep(0.3)
                core.mda.toggle_pause()
                assert core.mda.is_paused()
                status_changes.append(core.mda.status)
                time.sleep(0.3)
                core.mda.toggle_pause()
                assert not core.mda.is_paused()
                status_changes.append(core.mda.status)


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
                    "Pause has been requested, but sequenced acquisition "
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
        with qtbot.waitSignal(core.mda.events.sequenceFinished, timeout=10000):
            acq_thread = core.run_mda(sequence)
            assert core.mda.is_running()
            paused = False
            while acq_thread.is_alive():
                if not paused:
                    paused = True
                    time.sleep(0.2)
                    core.mda.toggle_pause()
                    assert core.mda.is_paused()
                    assert core.mda.is_running()
                    # to stop the sequence faster
                    time.sleep(0.1)
                    core.mda.cancel()
                    assert not core.mda.is_running()
                    assert not core.mda.is_paused()
                    assert core.mda.is_cancel_requested()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)


def test_status_persistence_after_completion(core: CMMCorePlus) -> None:
    """Test that terminal status persists after sequence finishes."""
    # This is a synchronous test (no threading)
    sequence = MDASequence(channels=["DAPI"], time_plan={"interval": 0.1, "loops": 2})

    # Run synchronously
    core.mda.run(sequence)

    # Status should be COMPLETED
    assert core.mda.status == RunStatus.COMPLETED
    assert not core.mda.is_running()


def test_toggle_pause_when_not_running(core: CMMCorePlus) -> None:
    """Test that toggle_pause is a no-op when not running."""
    assert core.mda.status == RunStatus.IDLE

    # Should be no-op
    core.mda.toggle_pause()

    # Status should still be IDLE
    assert core.mda.status == RunStatus.IDLE
    assert not core.mda.is_paused()


def test_cancel_when_not_running(core: CMMCorePlus) -> None:
    """Test that cancel is a no-op when not running."""
    assert core.mda.status == RunStatus.IDLE

    # Should be no-op
    core.mda.cancel()

    # Status should still be IDLE
    assert core.mda.status == RunStatus.IDLE


def test_remaining_wait_time_calculation_with_pause(core: CMMCorePlus) -> None:
    """Test that _get_remaining_wait_time recalculates with updated _paused_time.

    This verifies the comment in _get_remaining_wait_time:
    'We calculate remaining_wait_time fresh each iteration using
    event.min_start_time + self._paused_time to ensure it stays correct
    even when self._paused_time changes during pause.'

    This is a unit test that directly tests the calculation logic,
    simulating the scenario where pause time accumulates during a wait interval.
    """
    # Set up the runner with a known state
    runner = core.mda
    min_start_time = 4.0  # Event should start 4 seconds after t0

    # Simulate starting the sequence
    runner._t0 = time.perf_counter()
    initial_t0 = runner._t0

    # Initially, no pause time has accumulated
    runner._paused_time = 0.0

    # Calculate remaining wait time - should be close to 4.0 seconds
    remaining_1 = runner._get_remaining_wait_time(min_start_time)
    assert 3.9 < remaining_1 <= 4.0, f"Expected remaining time ~4.0s, got {remaining_1}"

    # Simulate some time passing (1.0 seconds)
    time.sleep(1.0)

    # Without any pause, remaining time should decrease by ~1s
    # More lenient bounds since sleep timing can vary
    remaining_2 = runner._get_remaining_wait_time(min_start_time)
    assert 2.7 < remaining_2 < 3.2, f"Expected remaining time ~3.0s, got {remaining_2}"

    # Now simulate a pause accumulating (add 2.0 seconds of pause time)
    # This simulates what happens when _handle_pause_state() accumulates time
    runner._paused_time = 2.0

    # The remaining wait time should be recalculated using the NEW paused_time
    # Formula: min_start_time + paused_time - elapsed
    # Expected: 4.0 + 2.0 - ~1.0 = ~5.0 seconds (but elapsed may vary slightly)
    remaining_3 = runner._get_remaining_wait_time(min_start_time)
    elapsed = time.perf_counter() - initial_t0
    expected = min_start_time + runner._paused_time - elapsed
    assert abs(remaining_3 - expected) < 0.2, (
        f"Expected remaining time to be recalculated with new paused_time. "
        f"Expected ~{expected:.2f}s, got {remaining_3:.2f}s. "
        f"This confirms that the calculation uses the CURRENT paused_time value."
    )

    # Verify that the remaining time INCREASED compared to remaining_2
    # because we added pause time (this is the key behavior)
    assert remaining_3 > remaining_2, (
        f"After adding paused_time, remaining wait should increase. "
        f"Before pause: {remaining_2:.2f}s, after pause: {remaining_3:.2f}s. "
        f"This demonstrates that _get_remaining_wait_time recalculates "
        f"fresh each time using the current _paused_time value, maintaining "
        f"the correct interval duration even when paused."
    )

    # Verify the timing makes sense: with 2s pause added to 4s interval,
    # and ~1s already elapsed, we should have ~5s remaining
    # More lenient bounds to account for sleep timing variations
    assert 4.7 < remaining_3 < 5.3, (
        f"Expected remaining time ~5.0s (4s interval + 2s pause - ~1s elapsed), "
        f"got {remaining_3:.2f}s"
    )

    # Clean up
    runner._paused_time = 0.0
