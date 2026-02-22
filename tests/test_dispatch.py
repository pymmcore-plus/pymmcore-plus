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
    _ConsumerWorker,
    _FrameMessage,
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


class BlockingConsumer(SimpleConsumer):
    """Consumer that blocks until released. Guarantees queue stays full."""

    def __init__(self) -> None:
        super().__init__()
        self.gate = threading.Event()

    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        self.gate.wait()
        super().frame(img, event, meta)


def test_backpressure_drop_newest() -> None:
    """DROP_NEWEST policy drops new frames when queue is full."""
    consumer = BlockingConsumer()
    policy = RunPolicy(
        backpressure=BackpressurePolicy.DROP_NEWEST,
        critical_queue=2,
    )
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("blocked", consumer, critical=True))
    dispatcher.start(seq, {})

    # Submit many frames while consumer is blocked — queue stays full
    for i in range(10):
        dispatcher.submit(*_make_frame(i))

    consumer.gate.set()
    report = dispatcher.close(seq, RunStatus.COMPLETED)
    cr = report.consumer_reports[0]
    assert cr.dropped > 0
    assert cr.submitted == 10


def test_backpressure_drop_oldest() -> None:
    """DROP_OLDEST policy drops old frames when queue is full."""
    consumer = BlockingConsumer()
    policy = RunPolicy(
        backpressure=BackpressurePolicy.DROP_OLDEST,
        critical_queue=2,
    )
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("blocked", consumer, critical=True))
    dispatcher.start(seq, {})

    for i in range(10):
        dispatcher.submit(*_make_frame(i))

    consumer.gate.set()
    report = dispatcher.close(seq, RunStatus.COMPLETED)
    cr = report.consumer_reports[0]
    assert cr.dropped > 0


def test_backpressure_fail() -> None:
    """FAIL policy raises BufferError when queue is full."""
    consumer = BlockingConsumer()
    policy = RunPolicy(
        backpressure=BackpressurePolicy.FAIL,
        critical_queue=1,
    )
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("blocked", consumer, critical=True))
    dispatcher.start(seq, {})

    dispatcher.submit(*_make_frame(0))

    with pytest.raises(BufferError, match="queue full"):
        for i in range(1, 100):
            dispatcher.submit(*_make_frame(i))

    consumer.gate.set()
    dispatcher.close(seq, RunStatus.FAILED)


def test_queue_status() -> None:
    """queue_status() returns correct pending/capacity info."""
    consumer = SimpleConsumer()
    policy = RunPolicy(critical_queue=10)
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("slow", consumer, critical=True))
    dispatcher.start(seq, {})

    status = dispatcher.queue_status()
    assert "slow" in status
    pending, capacity = status["slow"]
    assert capacity == 10
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
        def setup(self, seq: Any, meta: Any) -> None:  # type: ignore
            raise RuntimeError("setup failed")

    policy = RunPolicy(critical_error=CriticalErrorPolicy.RAISE)
    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("bad", BadSetupConsumer(), critical=True))  # type: ignore

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


def test_setup_error_critical_cancel_requests_cancel() -> None:
    """Critical setup error with CANCEL policy requests cancellation."""

    class BadSetupConsumer(SimpleConsumer):
        def setup(self, seq: Any, meta: Any) -> None:
            raise RuntimeError("setup failed")

    policy = RunPolicy(critical_error=CriticalErrorPolicy.CANCEL)
    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("bad", BadSetupConsumer(), critical=True))

    dispatcher.start(MDASequence(), {})
    assert dispatcher.should_cancel()
    dispatcher.close(MDASequence(), RunStatus.CANCELED)


def test_legacy_adapter_does_not_mask_typeerror() -> None:
    """_LegacyAdapter does not hide callback-internal TypeError exceptions."""

    class BuggyHandler:
        def frameReady(self, img: np.ndarray, event: MDAEvent, meta: dict) -> None:
            raise TypeError("internal error")

    adapter = _LegacyAdapter(BuggyHandler())

    with pytest.raises(TypeError, match="internal error"):
        adapter.frame(np.array([1]), MDAEvent(), {})


def test_concurrent_consumers() -> None:
    """Multiple consumers process frames concurrently on separate threads."""
    thread_names: list[str] = []
    lock = threading.Lock()

    class ThreadTracker(SimpleConsumer):
        def frame(self, img: Any, event: Any, meta: Any) -> None:
            with lock:
                thread_names.append(threading.current_thread().name)

    seq = MDASequence()
    dispatcher = FrameDispatcher()

    for i in range(3):
        dispatcher.add_consumer(ConsumerSpec(f"t{i}", ThreadTracker(), critical=True))

    dispatcher.start(seq, {})
    dispatcher.submit(*_make_frame())
    dispatcher.close(seq, RunStatus.COMPLETED)

    # Each consumer should have processed on its own thread
    assert len(thread_names) == 3
    unique_threads = set(thread_names)
    assert len(unique_threads) == 3
    for name in unique_threads:
        assert name.startswith("mda-t")


def _msg(val: int = 0) -> _FrameMessage:
    return _FrameMessage(np.array([val]), MDAEvent(), {"v": val})


def test_stop_does_not_block_on_full_queue() -> None:
    """worker.stop() returns in bounded time even when queue is full and idle."""
    policy = RunPolicy(
        critical_error=CriticalErrorPolicy.RAISE,
        backpressure=BackpressurePolicy.BLOCK,
        critical_queue=2,
    )
    spec = ConsumerSpec("test", SimpleConsumer(), critical=True)
    worker = _ConsumerWorker(spec, policy)
    # Don't start the worker thread — simulate it having already exited.

    worker.queue.put(_msg(0))
    worker.queue.put(_msg(1))
    assert worker.queue.full()

    done = threading.Event()

    def _stop() -> None:
        worker.stop()
        done.set()

    t = threading.Thread(target=_stop, daemon=True)
    t.start()
    assert done.wait(timeout=3), "worker.stop() blocked on full queue"


def test_cancel_signal_comes_after_started() -> None:
    """sequenceCanceled is always emitted after sequenceStarted."""
    from pymmcore_plus.mda._runner import MDARunner

    class FailSetup:
        def setup(self, seq: Any, meta: Any) -> None:
            raise RuntimeError("setup failed")

        def frame(self, img: Any, event: Any, meta: Any) -> None:
            pass

        def finish(self, seq: Any, status: Any) -> None:
            pass

    class MinimalEngine:
        def setup_sequence(self, sequence: MDASequence) -> dict:
            return {}

        def setup_event(self, event: MDAEvent) -> None:
            pass

        def exec_event(self, event: MDAEvent) -> Any:
            return ()

        def event_iterator(self, events: Any) -> Any:
            return iter(events)

        def teardown_event(self, event: MDAEvent) -> None:
            pass

        def teardown_sequence(self, sequence: MDASequence) -> None:
            pass

    runner = MDARunner()
    runner.set_engine(MinimalEngine())

    signal_log: list[str] = []
    runner.events.sequenceStarted.connect(lambda *a: signal_log.append("started"))
    runner.events.sequenceCanceled.connect(lambda *a: signal_log.append("canceled"))
    runner.events.sequenceFinished.connect(lambda *a: signal_log.append("finished"))

    policy = RunPolicy(critical_error=CriticalErrorPolicy.CANCEL)
    runner.run(
        [MDAEvent()],
        consumers=[ConsumerSpec("bad", FailSetup(), critical=True)],
        policy=policy,
    )

    assert "started" in signal_log
    assert "canceled" in signal_log
    assert signal_log.index("started") < signal_log.index("canceled")


def test_finish_not_called_when_setup_failed() -> None:
    """Consumers excluded by setup() failure don't receive finish()."""

    class FailingConsumer:
        def __init__(self) -> None:
            self.finish_called = False

        def setup(self, seq: Any, meta: Any) -> None:
            raise RuntimeError("setup failed")

        def frame(self, img: Any, event: Any, meta: Any) -> None:
            pass

        def finish(self, seq: Any, status: Any) -> None:
            self.finish_called = True

    consumer = FailingConsumer()
    policy = RunPolicy(critical_error=CriticalErrorPolicy.CANCEL)

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("bad", consumer, critical=True))

    seq = MDASequence()
    dispatcher.start(seq, {})
    assert len(dispatcher._workers) == 0

    dispatcher.close(seq, RunStatus.CANCELED)
    assert not consumer.finish_called


def test_report_counters_consistent_under_load() -> None:
    """Report counters are consistent after many concurrent submits."""
    policy = RunPolicy(
        backpressure=BackpressurePolicy.BLOCK,
        critical_queue=256,
    )
    consumer = SlowConsumer(delay=0.001)
    spec = ConsumerSpec("test", consumer, critical=True)
    worker = _ConsumerWorker(spec, policy)
    worker.start()

    n_frames = 200
    for i in range(n_frames):
        worker.submit(_msg(i))

    worker.stop()
    worker.join(timeout=5)

    assert worker.report.submitted == n_frames
    assert worker.report.processed == n_frames
    assert worker.report.dropped == 0


# ---------------------------------------------------------------------------
# finish() bug tests (currently failing — demonstrate bugs to fix)
# ---------------------------------------------------------------------------


class FinishErrorConsumer(SimpleConsumer):
    """Consumer that raises on finish()."""

    def __init__(self, error: Exception | None = None) -> None:
        super().__init__()
        self.error = error or RuntimeError("finish failed")

    def finish(self, sequence: MDASequence, status: RunStatus) -> None:
        super().finish(sequence, status)
        raise self.error


def test_finish_error_raise_does_not_skip_other_consumers() -> None:
    """finish() error with RAISE should not prevent other consumers' finish()."""
    c1 = FinishErrorConsumer()
    c2 = SimpleConsumer()
    policy = RunPolicy(critical_error=CriticalErrorPolicy.RAISE)
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("bad", c1, critical=True))
    dispatcher.add_consumer(ConsumerSpec("good", c2, critical=True))
    dispatcher.start(seq, {})

    # Both consumers should get finish() called, even if the first raises.
    with pytest.raises(ConsumerDispatchError):
        dispatcher.close(seq, RunStatus.COMPLETED)

    assert len(c1.finish_calls) == 1
    assert len(c2.finish_calls) == 1, (
        "Second consumer's finish() was skipped because first consumer raised"
    )


def test_finish_error_cancel_requests_cancel() -> None:
    """finish() error with CANCEL policy should set cancel flag."""
    consumer = FinishErrorConsumer()
    policy = RunPolicy(critical_error=CriticalErrorPolicy.CANCEL)
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("bad", consumer, critical=True))
    dispatcher.start(seq, {})
    dispatcher.close(seq, RunStatus.COMPLETED)

    assert dispatcher.should_cancel()


def test_finish_error_continue_logs() -> None:
    """finish() error with CONTINUE policy should not raise."""
    consumer = FinishErrorConsumer()
    policy = RunPolicy(critical_error=CriticalErrorPolicy.CONTINUE)
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("bad", consumer, critical=True))
    dispatcher.start(seq, {})

    # Should not raise
    report = dispatcher.close(seq, RunStatus.COMPLETED)
    assert len(consumer.finish_calls) == 1
    assert report.status == RunStatus.COMPLETED


# ---------------------------------------------------------------------------
# Gap-filling tests
# ---------------------------------------------------------------------------


def test_finish_error_noncritical_disconnect() -> None:
    """Non-critical finish() error with DISCONNECT should not raise."""
    consumer = FinishErrorConsumer()
    policy = RunPolicy(noncritical_error=NonCriticalErrorPolicy.DISCONNECT)
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("obs", consumer, critical=False))
    dispatcher.start(seq, {})

    report = dispatcher.close(seq, RunStatus.COMPLETED)
    assert len(consumer.finish_calls) == 1
    assert report.status == RunStatus.COMPLETED


def test_finish_error_noncritical_log() -> None:
    """Non-critical finish() error with LOG should not raise."""
    consumer = FinishErrorConsumer()
    policy = RunPolicy(noncritical_error=NonCriticalErrorPolicy.LOG)
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("obs", consumer, critical=False))
    dispatcher.start(seq, {})

    report = dispatcher.close(seq, RunStatus.COMPLETED)
    assert len(consumer.finish_calls) == 1
    assert report.status == RunStatus.COMPLETED


def test_multiple_critical_consumers_failing() -> None:
    """Multiple critical consumers both failing — all errors collected."""
    c1 = ErrorConsumer(ValueError("error1"))
    c2 = ErrorConsumer(ValueError("error2"))
    policy = RunPolicy(critical_error=CriticalErrorPolicy.CONTINUE)
    seq = MDASequence()

    dispatcher = FrameDispatcher(policy)
    dispatcher.add_consumer(ConsumerSpec("c1", c1, critical=True))
    dispatcher.add_consumer(ConsumerSpec("c2", c2, critical=True))
    dispatcher.start(seq, {})
    dispatcher.submit(*_make_frame())

    report = dispatcher.close(seq, RunStatus.COMPLETED)
    assert len(report.consumer_reports) == 2
    assert len(report.consumer_reports[0].errors) == 1
    assert len(report.consumer_reports[1].errors) == 1


def test_legacy_adapter_setup_error_propagates() -> None:
    """_LegacyAdapter propagates errors from sequenceStarted."""

    class BadStartHandler:
        def sequenceStarted(self, seq: Any, meta: Any) -> None:
            raise RuntimeError("start failed")

        def frameReady(self, img: Any) -> None:
            pass

    adapter = _LegacyAdapter(BadStartHandler())
    with pytest.raises(RuntimeError, match="start failed"):
        adapter.setup(MDASequence(), {})


def test_legacy_adapter_finish_error_propagates() -> None:
    """_LegacyAdapter propagates errors from sequenceFinished."""

    class BadFinishHandler:
        def sequenceFinished(self, seq: Any) -> None:
            raise RuntimeError("finish failed")

        def frameReady(self, img: Any) -> None:
            pass

    adapter = _LegacyAdapter(BadFinishHandler())
    with pytest.raises(RuntimeError, match="finish failed"):
        adapter.finish(MDASequence(), RunStatus.COMPLETED)
