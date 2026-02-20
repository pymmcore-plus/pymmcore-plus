"""Tests for the frame dispatch system."""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
from useq import MDAEvent, MDASequence

from pymmcore_plus.mda._dispatch import (
    BackpressurePolicy,
    ConsumerDispatchError,
    ConsumerReport,
    ConsumerSpec,
    CriticalErrorPolicy,
    FrameDispatcher,
    NonCriticalErrorPolicy,
    RunPolicy,
    RunReport,
    RunStatus,
    _LegacyAdapter,
    _SignalRelay,
)


class SimpleConsumer:
    """Test consumer that records calls."""

    def __init__(self) -> None:
        self.setup_calls: list[tuple] = []
        self.frame_calls: list[tuple] = []
        self.finish_calls: list[tuple] = []

    def setup(self, sequence: MDASequence, meta: dict[str, Any]) -> None:
        self.setup_calls.append((sequence, meta))

    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        self.frame_calls.append((img, event, meta))

    def finish(self, sequence: MDASequence, status: RunStatus) -> None:
        self.finish_calls.append((sequence, status))


class ErrorConsumer(SimpleConsumer):
    """Consumer that raises on frame()."""

    def __init__(self, error: Exception | None = None) -> None:
        super().__init__()
        self.error = error or ValueError("test error")

    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        super().frame(img, event, meta)
        raise self.error


class SlowConsumer(SimpleConsumer):
    """Consumer that sleeps on frame()."""

    def __init__(self, delay: float = 0.1) -> None:
        super().__init__()
        self.delay = delay

    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        super().frame(img, event, meta)
        time.sleep(self.delay)


def _make_frame(
    value: int = 0,
) -> tuple[np.ndarray, MDAEvent, dict[str, Any]]:
    return (np.array([value]), MDAEvent(), {"value": value})


def test_basic_dispatch() -> None:
    """Consumers receive frames submitted to the dispatcher."""
    consumer = SimpleConsumer()
    spec = ConsumerSpec("test", consumer)
    seq = MDASequence()

    dispatcher = FrameDispatcher()
    dispatcher.add_consumer(spec)
    dispatcher.start(seq, {"key": "val"})

    img, event, meta = _make_frame(42)
    dispatcher.submit(img, event, meta)

    report = dispatcher.close(seq, RunStatus.COMPLETED)

    assert len(consumer.setup_calls) == 1
    assert consumer.setup_calls[0] == (seq, {"key": "val"})
    assert len(consumer.frame_calls) == 1
    assert consumer.frame_calls[0][2]["value"] == 42
    assert len(consumer.finish_calls) == 1
    assert consumer.finish_calls[0][1] == RunStatus.COMPLETED

    assert report.status == RunStatus.COMPLETED
    assert len(report.consumer_reports) == 1
    assert report.consumer_reports[0].submitted == 1
    assert report.consumer_reports[0].processed == 1


def test_multiple_consumers() -> None:
    """Multiple consumers all receive each frame."""
    consumers = [SimpleConsumer() for _ in range(3)]
    seq = MDASequence()

    dispatcher = FrameDispatcher()
    for i, c in enumerate(consumers):
        dispatcher.add_consumer(ConsumerSpec(f"c{i}", c))

    dispatcher.start(seq, {})
    for i in range(5):
        dispatcher.submit(*_make_frame(i))
    report = dispatcher.close(seq, RunStatus.COMPLETED)

    for c in consumers:
        assert len(c.frame_calls) == 5

    assert len(report.consumer_reports) == 3
    for cr in report.consumer_reports:
        assert cr.submitted == 5
        assert cr.processed == 5


def test_critical_error_raise() -> None:
    """Critical consumer error with RAISE policy raises after close()."""
    consumer = ErrorConsumer()
    policy = RunPolicy(critical_error=CriticalErrorPolicy.RAISE)
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("failing", consumer, critical=True))
    dispatcher.start(seq, {})
    dispatcher.submit(*_make_frame())

    with pytest.raises(ConsumerDispatchError, match="failing"):
        dispatcher.close(seq, RunStatus.COMPLETED)


def test_critical_error_cancel() -> None:
    """Critical consumer error with CANCEL policy sets should_cancel."""
    consumer = ErrorConsumer()
    policy = RunPolicy(critical_error=CriticalErrorPolicy.CANCEL)
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("failing", consumer, critical=True))
    dispatcher.start(seq, {})
    dispatcher.submit(*_make_frame())

    # Give worker thread time to process
    time.sleep(0.1)
    assert dispatcher.should_cancel()

    report = dispatcher.close(seq, RunStatus.CANCELED)
    assert report.status == RunStatus.CANCELED


def test_critical_error_continue() -> None:
    """Critical consumer error with CONTINUE policy logs and continues."""
    consumer = ErrorConsumer()
    policy = RunPolicy(critical_error=CriticalErrorPolicy.CONTINUE)
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("failing", consumer, critical=True))
    dispatcher.start(seq, {})

    for i in range(3):
        dispatcher.submit(*_make_frame(i))

    report = dispatcher.close(seq, RunStatus.COMPLETED)
    cr = report.consumer_reports[0]
    assert len(cr.errors) == 3
    assert cr.submitted == 3


def test_noncritical_error_log() -> None:
    """Non-critical consumer error with LOG policy keeps consumer running."""
    consumer = ErrorConsumer()
    policy = RunPolicy(noncritical_error=NonCriticalErrorPolicy.LOG)
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("observer", consumer, critical=False))
    dispatcher.start(seq, {})

    for i in range(3):
        dispatcher.submit(*_make_frame(i))

    report = dispatcher.close(seq, RunStatus.COMPLETED)
    assert not dispatcher.should_cancel()
    cr = report.consumer_reports[0]
    assert len(cr.errors) == 3


def test_noncritical_error_disconnect() -> None:
    """Non-critical consumer error with DISCONNECT stops delivery."""
    consumer = ErrorConsumer()
    policy = RunPolicy(noncritical_error=NonCriticalErrorPolicy.DISCONNECT)
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("observer", consumer, critical=False))
    dispatcher.start(seq, {})

    dispatcher.submit(*_make_frame(0))
    time.sleep(0.1)  # let the worker process and disconnect

    # This submit should be ignored (consumer disconnected)
    dispatcher.submit(*_make_frame(1))

    report = dispatcher.close(seq, RunStatus.COMPLETED)
    cr = report.consumer_reports[0]
    # Only 1 frame actually processed (errored)
    assert cr.submitted <= 2
    assert len(cr.errors) == 1


def test_backpressure_drop_newest() -> None:
    """DROP_NEWEST policy drops new frames when queue is full."""
    slow = SlowConsumer(delay=0.5)
    policy = RunPolicy(
        backpressure=BackpressurePolicy.DROP_NEWEST,
        critical_queue=2,
    )
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("slow", slow, critical=True))
    dispatcher.start(seq, {})

    # Submit many frames quickly (queue capacity is 2)
    for i in range(10):
        dispatcher.submit(*_make_frame(i))

    report = dispatcher.close(seq, RunStatus.COMPLETED)
    cr = report.consumer_reports[0]
    assert cr.dropped > 0
    assert cr.submitted == 10


def test_backpressure_drop_oldest() -> None:
    """DROP_OLDEST policy drops old frames when queue is full."""
    slow = SlowConsumer(delay=0.5)
    policy = RunPolicy(
        backpressure=BackpressurePolicy.DROP_OLDEST,
        critical_queue=2,
    )
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("slow", slow, critical=True))
    dispatcher.start(seq, {})

    for i in range(10):
        dispatcher.submit(*_make_frame(i))

    report = dispatcher.close(seq, RunStatus.COMPLETED)
    cr = report.consumer_reports[0]
    assert cr.dropped > 0


def test_backpressure_fail() -> None:
    """FAIL policy raises BufferError when queue is full."""
    slow = SlowConsumer(delay=1.0)
    policy = RunPolicy(
        backpressure=BackpressurePolicy.FAIL,
        critical_queue=1,
    )
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("slow", slow, critical=True))
    dispatcher.start(seq, {})

    # First frame goes in fine
    dispatcher.submit(*_make_frame(0))

    # Subsequent frames should eventually overflow
    with pytest.raises(BufferError, match="queue full"):
        for i in range(1, 100):
            dispatcher.submit(*_make_frame(i))

    dispatcher.close(seq, RunStatus.FAILED)


def test_queue_status() -> None:
    """queue_status() returns correct pending/capacity info."""
    slow = SlowConsumer(delay=0.5)
    policy = RunPolicy(critical_queue=10)
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("slow", slow, critical=True))
    dispatcher.start(seq, {})

    for i in range(5):
        dispatcher.submit(*_make_frame(i))

    status = dispatcher.queue_status()
    assert "slow" in status
    pending, capacity = status["slow"]
    assert capacity == 10
    # pending might be less than 5 if the worker already processed some
    assert pending >= 0

    dispatcher.close(seq, RunStatus.COMPLETED)


def test_run_report() -> None:
    """RunReport has correct timing and consumer data."""
    consumer = SimpleConsumer()
    seq = MDASequence()

    dispatcher = FrameDispatcher()
    dispatcher.add_consumer(ConsumerSpec("test", consumer))
    dispatcher.start(seq, {})
    dispatcher.submit(*_make_frame())
    report = dispatcher.close(seq, RunStatus.COMPLETED)

    assert isinstance(report, RunReport)
    assert report.status == RunStatus.COMPLETED
    assert report.finished_at >= report.started_at
    assert len(report.consumer_reports) == 1


def test_legacy_adapter_frameready() -> None:
    """_LegacyAdapter wraps frameReady/sequenceStarted/sequenceFinished."""

    class LegacyHandler:
        def __init__(self) -> None:
            self.frames: list = []
            self.started = False
            self.finished = False

        def sequenceStarted(self, seq: Any, meta: Any) -> None:
            self.started = True

        def frameReady(self, img: np.ndarray, event: MDAEvent, meta: dict) -> None:
            self.frames.append(img)

        def sequenceFinished(self, seq: Any) -> None:
            self.finished = True

    handler = LegacyHandler()
    adapter = _LegacyAdapter(handler)

    seq = MDASequence()
    adapter.setup(seq, {})
    assert handler.started

    img = np.array([1, 2, 3])
    adapter.frame(img, MDAEvent(), {})
    assert len(handler.frames) == 1

    adapter.finish(seq, RunStatus.COMPLETED)
    assert handler.finished


def test_legacy_adapter_fewer_args() -> None:
    """_LegacyAdapter handles handlers with fewer args."""

    class MinimalHandler:
        def __init__(self) -> None:
            self.called = False

        def frameReady(self) -> None:
            self.called = True

    handler = MinimalHandler()
    adapter = _LegacyAdapter(handler)

    adapter.frame(np.array([1]), MDAEvent(), {})
    assert handler.called


def test_signal_relay() -> None:
    """_SignalRelay emits frameReady on the signals object."""
    signals = MagicMock()
    relay = _SignalRelay(signals)

    img = np.array([1])
    event = MDAEvent()
    meta = {"key": "val"}

    relay.frame(img, event, meta)
    signals.frameReady.emit.assert_called_once_with(img, event, meta)


def test_consumer_report_defaults() -> None:
    """ConsumerReport starts with zero counters."""
    report = ConsumerReport(name="test")
    assert report.submitted == 0
    assert report.processed == 0
    assert report.dropped == 0
    assert report.errors == []


def test_run_status_values() -> None:
    """RunStatus enum has expected values."""
    assert RunStatus.COMPLETED == "completed"
    assert RunStatus.CANCELED == "canceled"
    assert RunStatus.FAILED == "failed"


def test_setup_error_critical_raise() -> None:
    """Critical consumer setup error with RAISE re-raises."""

    class BadSetupConsumer(SimpleConsumer):
        def setup(self, seq: Any, meta: Any) -> None:
            raise RuntimeError("setup failed")

    policy = RunPolicy(critical_error=CriticalErrorPolicy.RAISE)
    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("bad", BadSetupConsumer(), critical=True))

    with pytest.raises(ConsumerDispatchError, match="bad"):
        dispatcher.start(MDASequence(), {})


def test_setup_error_noncritical_disconnect() -> None:
    """Non-critical consumer setup error with DISCONNECT excludes it."""

    class BadSetupConsumer(SimpleConsumer):
        def setup(self, seq: Any, meta: Any) -> None:
            raise RuntimeError("setup failed")

    policy = RunPolicy(noncritical_error=NonCriticalErrorPolicy.DISCONNECT)
    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("bad", BadSetupConsumer(), critical=False))

    # Should not raise, but consumer should be excluded
    dispatcher.start(MDASequence(), {})
    # No workers created for the excluded consumer
    assert len(dispatcher._workers) == 0
    dispatcher.close(MDASequence(), RunStatus.COMPLETED)


def test_concurrent_consumers() -> None:
    """Multiple consumers process frames concurrently on separate threads."""
    thread_names: list[str] = []
    lock = threading.Lock()

    class ThreadTracker(SimpleConsumer):
        def frame(self, img: Any, event: Any, meta: Any) -> None:
            with lock:
                thread_names.append(threading.current_thread().name)
            time.sleep(0.01)

    seq = MDASequence()
    dispatcher = FrameDispatcher()

    for i in range(3):
        dispatcher.add_consumer(ConsumerSpec(f"t{i}", ThreadTracker(), critical=True))

    dispatcher.start(seq, {})
    dispatcher.submit(*_make_frame())
    time.sleep(0.1)
    dispatcher.close(seq, RunStatus.COMPLETED)

    # Each consumer should have processed on its own thread
    assert len(thread_names) == 3
    unique_threads = set(thread_names)
    assert len(unique_threads) == 3
    for name in unique_threads:
        assert name.startswith("mda-t")
