"""Tests for MDA runner state management."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest
import useq

from pymmcore_plus.mda._runner import AcqState, FinishReason

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
            runner.toggle_pause()
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
    phases: list[AcqState] = []

    def _record_phase(phase: AcqState) -> None:
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
    assert AcqState.WAITING in phases
    assert AcqState.ACQUIRING in phases
    assert AcqState.FINISHING in phases
    # should end at IDLE
    assert runner.status.phase == AcqState.IDLE
    assert runner.status.finish_reason == FinishReason.COMPLETED


def test_finish_reason_completed(core: CMMCorePlus) -> None:
    """Normal run sets finish_reason to COMPLETED."""
    runner = core.mda
    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=2))
    runner.run(seq)

    assert runner.status.phase == AcqState.IDLE
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

    assert runner.status.phase == AcqState.IDLE
    assert runner.status.finish_reason == FinishReason.ERRORED


def test_cancel_from_idle_is_noop(core: CMMCorePlus) -> None:
    """Calling cancel() when IDLE should not change state."""
    runner = core.mda
    assert runner.status.phase == AcqState.IDLE

    runner.cancel()

    assert runner.status.phase == AcqState.IDLE
    assert runner.status.finish_reason is None
    assert not runner.status.cancel_requested


def test_toggle_pause_from_idle_is_noop(core: CMMCorePlus) -> None:
    """Calling toggle_pause() when IDLE should not change state."""
    runner = core.mda
    pause_mock = Mock()
    runner.events.sequencePauseToggled.connect(pause_mock)

    runner.toggle_pause()

    assert runner.status.phase == AcqState.IDLE
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
            runner.toggle_pause()
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
        time_plan=useq.TIntervalLoops(interval=10, loops=3),
    )
    runner.run(seq)

    cancel_mock.assert_called_once()
    assert runner.status.finish_reason == FinishReason.CANCELED
