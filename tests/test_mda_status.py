"""Tests for MDA runner state management."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest
import useq

from pymmcore_plus.mda._runner import FinishReason, RunState

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


@pytest.mark.parametrize("hardware_seq", [True, False])
def test_pause_and_cancel_mid_sequence(
    core: CMMCorePlus, caplog: pytest.LogCaptureFixture, hardware_seq: bool
) -> None:
    """Pause then cancel mid-sequence stops acquisition early."""
    runner = core.mda
    runner.engine.use_hardware_sequencing = hardware_seq

    frame_count = 0

    cancel_mock = Mock()
    runner.events.sequenceCanceled.connect(cancel_mock)

    @runner.events.frameReady.connect
    def _on_frame() -> None:
        nonlocal frame_count
        frame_count += 1
        if frame_count == 1 and hardware_seq:
            runner.set_paused(True)
        elif frame_count == 3:
            runner.cancel()

    sequence = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=50))

    with caplog.at_level(logging.WARNING, logger="pymmcore-plus"):
        runner.run(sequence)

    assert frame_count < 50
    assert any("MDA Canceled:" in r.message for r in caplog.records)
    cancel_mock.assert_called_once()
    assert runner.status.finish_reason == "canceled"
    # hardware sequences can't truly pause, only warn
    if hardware_seq:
        assert any("cannot be yet paused" in r.message for r in caplog.records)


def test_state_transitions_through_normal_run(core: CMMCorePlus) -> None:
    """Track phase transitions through a complete run."""
    runner = core.mda
    phases: list[RunState] = []

    def _record_phase(phase: RunState) -> None:
        if not phases or phases[-1] != phase:
            phases.append(phase)

    @runner.events.sequenceStarted.connect
    def _on_started(seq: object, meta: object) -> None:
        _record_phase(runner.status.phase)

    @runner.events.eventStarted.connect
    def _on_event(event: object) -> None:
        _record_phase(runner.status.phase)

    @runner.events.frameReady.connect
    def _on_frame(*args: object) -> None:
        _record_phase(runner.status.phase)

    @runner.events.sequenceFinished.connect
    def _on_finished(seq: object) -> None:
        _record_phase(runner.status.phase)

    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=3))
    runner.run(seq)

    # WAITING (after sequenceStarted), ACQUIRING (eventStarted/frameReady), FINISHING
    assert RunState.WAITING in phases
    assert RunState.ACQUIRING in phases
    assert RunState.FINISHING in phases
    # should end at IDLE
    assert runner.status.phase == RunState.IDLE
    assert runner.status.finish_reason == FinishReason.COMPLETED


def test_finish_reason_completed(core: CMMCorePlus) -> None:
    """Normal run sets finish_reason to COMPLETED."""
    runner = core.mda
    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=2))
    runner.run(seq)

    assert runner.status.phase == RunState.IDLE
    assert runner.status.finish_reason == FinishReason.COMPLETED


def test_finish_reason_errored(core: CMMCorePlus) -> None:
    """Engine error sets finish_reason to ERRORED."""
    runner = core.mda

    class BrokenEngine:
        def setup_sequence(self, sequence: object) -> None: ...
        def setup_event(self, event: object) -> None:
            raise ValueError("hardware fault")

        def exec_event(self, event: object) -> None: ...

    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=2))
    with patch.object(runner, "_engine", BrokenEngine()):
        with pytest.raises(ValueError, match="hardware fault"):
            runner.run(seq)

    assert runner.status.phase == RunState.IDLE
    assert runner.status.finish_reason == FinishReason.ERRORED


def test_cancel_from_idle_is_noop(core: CMMCorePlus) -> None:
    """Calling cancel() when IDLE should not change state."""
    runner = core.mda
    assert runner.status.phase == RunState.IDLE

    runner.cancel()

    assert runner.status.phase == RunState.IDLE
    assert runner.status.finish_reason is None
    assert not runner.status.cancel_requested


def test_set_paused_from_idle_is_noop(core: CMMCorePlus) -> None:
    """Calling set_paused() when IDLE should not change state."""
    runner = core.mda
    pause_mock = Mock()
    runner.events.sequencePauseToggled.connect(pause_mock)

    runner.set_paused(True)

    assert runner.status.phase == RunState.IDLE
    assert not runner.is_paused()
    pause_mock.assert_not_called()


def test_cancel_from_paused(core: CMMCorePlus) -> None:
    """Cancel while paused should emit sequenceCanceled."""
    runner = core.mda
    cancel_mock = Mock()
    runner.events.sequenceCanceled.connect(cancel_mock)

    paused = False

    @runner.events.frameReady.connect
    def _on_frame(*args: object) -> None:
        nonlocal paused
        if not paused:
            paused = True
            runner.set_paused(True)
            # now in PAUSED → cancel immediately
            runner.cancel()

    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=50))
    runner.run(seq)

    cancel_mock.assert_called_once()
    assert runner.status.finish_reason == FinishReason.CANCELED


def test_cancel_from_waiting(core: CMMCorePlus) -> None:
    """Cancel while waiting between events should cancel immediately."""
    runner = core.mda
    cancel_mock = Mock()
    runner.events.sequenceCanceled.connect(cancel_mock)

    @runner.events.awaitingEvent.connect
    def _on_awaiting(event: object, remaining: float) -> None:
        runner.cancel()

    seq = useq.MDASequence(
        time_plan=useq.TIntervalLoops(interval=0.2, loops=3),
    )
    runner.run(seq)

    cancel_mock.assert_called_once()
    assert runner.status.finish_reason == FinishReason.CANCELED


def test_threaded_run_mda_cancel(core: CMMCorePlus) -> None:
    """Threaded run_mda path can be canceled and returns to IDLE."""
    runner = core.mda
    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0.1, loops=5))

    thread = core.run_mda(seq)

    deadline = time.perf_counter() + 2.0
    while (
        runner._state not in (RunState.WAITING, RunState.ACQUIRING)
        and time.perf_counter() < deadline
    ):
        time.sleep(0.005)

    assert runner.is_running()
    runner.cancel()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert runner.status.phase == RunState.IDLE
    assert runner.status.finish_reason == FinishReason.CANCELED


def test_cancel_from_preparing(core: CMMCorePlus) -> None:
    """Cancel while PREPARING should remain canceled after setup returns."""
    runner = core.mda
    cancel_mock = Mock()
    frame_mock = Mock()
    runner.events.sequenceCanceled.connect(cancel_mock)
    runner.events.frameReady.connect(frame_mock)

    original_setup_sequence = runner.engine.setup_sequence

    def _slow_setup(sequence: useq.MDASequence) -> object:
        time.sleep(0.2)
        assert runner.status.phase == RunState.PREPARING
        runner.cancel()
        return original_setup_sequence(sequence)

    with patch.object(runner.engine, "setup_sequence", side_effect=_slow_setup):
        seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=5))
        runner.run(seq)

    cancel_mock.assert_called_once()
    frame_mock.assert_not_called()
    assert runner.status.phase == RunState.IDLE
    assert runner.status.finish_reason == FinishReason.CANCELED


def test_pause_unpause_then_complete(core: CMMCorePlus) -> None:
    """Pause then unpause mid-sequence completes normally."""
    runner = core.mda
    pause_mock = Mock()
    runner.events.sequencePauseToggled.connect(pause_mock)

    frame_count = 0

    @runner.events.frameReady.connect
    def _on_frame(*args: object) -> None:
        nonlocal frame_count
        frame_count += 1
        if frame_count == 2:
            runner.set_paused(True)
            runner.set_paused(False)

    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=5))
    runner.run(seq)

    assert frame_count == 5
    assert runner.status.phase == RunState.IDLE
    assert runner.status.finish_reason == FinishReason.COMPLETED
    # paused then unpaused
    assert pause_mock.call_count == 2
