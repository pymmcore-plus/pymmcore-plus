"""Frame dispatch system for MDA runner.

Provides per-consumer worker threads, bounded queues, backpressure policies,
and critical/non-critical consumer semantics.
"""

from __future__ import annotations

import inspect
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from queue import Full, Queue
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np
    from useq import MDAEvent, MDASequence

    from .events import PMDASignaler

logger = logging.getLogger(__name__)

# ───────────────────────── Public Types ─────────────────────────


class RunStatus(str, Enum):
    """Status of a completed MDA run."""

    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"


@runtime_checkable
class FrameConsumer(Protocol):
    """Receives frames from the MDA runner."""

    def setup(self, sequence: MDASequence, meta: dict[str, Any]) -> None: ...
    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None: ...
    def finish(self, sequence: MDASequence, status: RunStatus) -> None: ...


@dataclass(slots=True)
class ConsumerSpec:
    """Registration info for a frame consumer."""

    name: str
    consumer: FrameConsumer
    critical: bool = True


# ───────────────────────── Policies ─────────────────────────


class CriticalErrorPolicy(str, Enum):
    """What to do when a critical consumer raises an error."""

    RAISE = "raise"  # propagate to caller after close()
    CANCEL = "cancel"  # stop acquisition, don't raise
    CONTINUE = "continue"  # log and continue


class NonCriticalErrorPolicy(str, Enum):
    """What to do when a non-critical consumer raises an error."""

    LOG = "log"  # log error, keep consumer running
    DISCONNECT = "disconnect"  # stop delivering to this consumer


class BackpressurePolicy(str, Enum):
    """What to do when a consumer's queue is full."""

    BLOCK = "block"  # block runner until queue has space
    DROP_OLDEST = "drop_oldest"
    DROP_NEWEST = "drop_newest"
    FAIL = "fail"  # raise BufferError


@dataclass(slots=True)
class RunPolicy:
    """Configuration for error handling and backpressure during an MDA run."""

    critical_error: CriticalErrorPolicy = CriticalErrorPolicy.RAISE
    noncritical_error: NonCriticalErrorPolicy = NonCriticalErrorPolicy.LOG
    backpressure: BackpressurePolicy = BackpressurePolicy.BLOCK
    critical_queue: int = 256
    observer_queue: int = 256


# ───────────────────────── Diagnostics ─────────────────────────


@dataclass(slots=True)
class ConsumerReport:
    """Per-consumer diagnostics from an MDA run."""

    name: str
    submitted: int = 0
    processed: int = 0
    dropped: int = 0
    errors: list[Exception] = field(default_factory=list)
    # TODO: submitted/dropped are written from the caller thread while
    # processed/errors are written from the worker thread.  This is safe under
    # the GIL but needs synchronization for free-threaded Python (PEP 703).


@dataclass(slots=True)
class RunReport:
    """Diagnostics from a completed MDA run."""

    status: RunStatus
    started_at: float
    finished_at: float
    consumer_reports: tuple[ConsumerReport, ...]


# ───────────────────────── Errors ─────────────────────────


class ConsumerDispatchError(Exception):
    """Wraps an exception from a critical consumer."""

    def __init__(self, consumer_name: str, original: Exception) -> None:
        self.consumer_name = consumer_name
        self.original = original
        super().__init__(f"Critical consumer {consumer_name!r} failed: {original}")


# ───────────────────────── Internal Message ─────────────────────────


@dataclass(slots=True)
class _FrameMessage:
    """Single frame shared (by reference) across all consumer queues."""

    img: np.ndarray
    event: MDAEvent
    meta: dict[str, Any]


# ───────────────────────── Consumer Worker ─────────────────────────

_STOP = object()


class _ConsumerWorker:
    """Per-consumer worker thread with bounded queue."""

    def __init__(self, spec: ConsumerSpec, policy: RunPolicy) -> None:
        self.name = spec.name
        self.callback = spec.consumer.frame
        self.critical = spec.critical
        self.policy = policy

        capacity = policy.critical_queue if spec.critical else policy.observer_queue
        self.queue: Queue[_FrameMessage | object] = Queue(maxsize=capacity)
        self.thread = threading.Thread(
            target=self._run, name=f"mda-{self.name}", daemon=True
        )

        self.report = ConsumerReport(name=self.name)
        self.fatal: ConsumerDispatchError | None = None
        self.stop_requested = threading.Event()
        self.disconnected = threading.Event()

    def start(self) -> None:
        self.thread.start()

    def submit(self, msg: _FrameMessage) -> bool:
        """Enqueue a frame. Returns False if the consumer is disconnected."""
        if self.disconnected.is_set() or self.stop_requested.is_set():
            return False

        self.report.submitted += 1
        bp = self.policy.backpressure

        if bp == BackpressurePolicy.BLOCK:
            self.queue.put(msg)  # blocks until space
            return True

        if bp == BackpressurePolicy.DROP_NEWEST:
            try:
                self.queue.put_nowait(msg)
            except Full:
                self.report.dropped += 1
            return True

        if bp == BackpressurePolicy.DROP_OLDEST:
            while True:
                try:
                    self.queue.put_nowait(msg)
                    return True
                except Full:
                    try:
                        self.queue.get_nowait()
                        self.report.dropped += 1
                    except Exception:  # pragma: no cover
                        pass

        # FAIL
        try:
            self.queue.put_nowait(msg)
        except Full:
            self.report.dropped += 1
            raise BufferError(
                f"Consumer {self.name!r} queue full ({self.queue.maxsize} items)"
            ) from None
        return True

    def stop(self) -> None:
        """Signal the worker to stop after draining its queue."""
        # Use put_nowait to avoid blocking forever if the queue is full
        # and the worker thread is already dead.
        while True:
            try:
                self.queue.put_nowait(_STOP)
                return
            except Full:
                try:
                    self.queue.get_nowait()
                except Exception:
                    pass

    def join(self, timeout: float | None = None) -> None:
        self.thread.join(timeout=timeout)

    def _run(self) -> None:
        """Thread loop: pull from queue and call consumer callback."""
        while True:
            item = self.queue.get()
            if item is _STOP:
                break
            msg: _FrameMessage = item  # type: ignore[assignment]
            try:
                self.callback(msg.img, msg.event, msg.meta)
                self.report.processed += 1
            except Exception as exc:
                self._handle_error(exc)
                if self.stop_requested.is_set() or self.disconnected.is_set():
                    break

    def _handle_error(self, exc: Exception) -> None:
        self.report.errors.append(exc)
        if self.critical:
            self._handle_critical_error(exc)
        else:
            self._handle_noncritical_error(exc)

    def _handle_critical_error(self, exc: Exception) -> None:
        policy = self.policy.critical_error
        if policy == CriticalErrorPolicy.CONTINUE:
            logger.exception("Critical consumer %r error (continuing):", self.name)
        elif policy == CriticalErrorPolicy.CANCEL:
            logger.error("Critical consumer %r error (canceling):", self.name)
            self.stop_requested.set()
        else:
            # RAISE: stop and store for later
            self.fatal = ConsumerDispatchError(self.name, exc)
            self.stop_requested.set()

    def _handle_noncritical_error(self, exc: Exception) -> None:
        policy = self.policy.noncritical_error
        if policy == NonCriticalErrorPolicy.LOG:
            logger.exception("Non-critical consumer %r error:", self.name)
        else:
            # DISCONNECT
            logger.warning(
                "Non-critical consumer %r disconnected due to error: %s",
                self.name,
                exc,
            )
            self.disconnected.set()


# ───────────────────────── Frame Dispatcher ─────────────────────────


class FrameDispatcher:
    """Fan-out dispatcher: the single object the runner interacts with."""

    def __init__(self, policy: RunPolicy | None = None) -> None:
        self.policy = policy or RunPolicy()
        self._specs: list[ConsumerSpec] = []
        self._surviving_specs: list[ConsumerSpec] = []
        self._workers: list[_ConsumerWorker] = []
        self.started_at: float = 0.0
        self._cancel_requested = False

    def add_consumer(self, spec: ConsumerSpec) -> None:
        """Register a consumer. Must be called before start()."""
        self._specs.append(spec)

    def start(self, sequence: MDASequence, meta: dict[str, Any]) -> None:
        """Call setup() on all consumers, then start worker threads."""
        self.started_at = time.perf_counter()
        surviving: list[ConsumerSpec] = []

        for spec in self._specs:
            try:
                spec.consumer.setup(sequence, meta)
            except Exception as exc:
                if not self._handle_lifecycle_error(spec, exc, "setup"):
                    continue
            surviving.append(spec)

        self._surviving_specs = surviving
        self._workers = [_ConsumerWorker(s, self.policy) for s in surviving]
        for w in self._workers:
            w.start()

    def submit(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        """Fan out one frame to all workers. Called from runner hot loop."""
        msg = _FrameMessage(img, event, meta)
        for worker in self._workers:
            worker.submit(msg)

    def should_cancel(self) -> bool:
        """Check if any critical worker requested cancellation."""
        return self._cancel_requested or any(
            w.stop_requested.is_set() for w in self._workers
        )

    def queue_status(self) -> dict[str, tuple[int, int]]:
        """Return {name: (pending, capacity)} per worker."""
        return {w.name: (w.queue.qsize(), w.queue.maxsize) for w in self._workers}

    def close(self, sequence: MDASequence, status: RunStatus) -> RunReport:
        """Stop workers, call finish() on all consumers, return report."""
        # Signal all workers to stop, then join
        for w in self._workers:
            w.stop()
        for w in self._workers:
            w.join(timeout=30)

        # Call finish() on all consumers that survived start().
        # Collect errors instead of raising immediately so every consumer
        # gets its finish() call even if an earlier one fails.
        finish_error: ConsumerDispatchError | None = None
        for spec in self._surviving_specs:
            try:
                spec.consumer.finish(sequence, status)
            except Exception as exc:
                if finish_error is None:
                    try:
                        self._handle_lifecycle_error(spec, exc, "finish")
                    except ConsumerDispatchError as cde:
                        finish_error = cde
                else:
                    logger.error(
                        "Consumer %r finish error (after prior failure): %s",
                        spec.name,
                        exc,
                    )

        # Collect reports
        reports = tuple(w.report for w in self._workers)
        finished_at = time.perf_counter()

        # Check for fatal errors (from frame processing or finish)
        fatal = finish_error or next(
            (w.fatal for w in self._workers if w.fatal is not None), None
        )

        report = RunReport(
            status=status,
            started_at=self.started_at,
            finished_at=finished_at,
            consumer_reports=reports,
        )

        if fatal is not None:
            raise fatal

        return report

    def _handle_lifecycle_error(
        self, spec: ConsumerSpec, exc: Exception, phase: str
    ) -> bool:
        """Handle error in setup/finish. Returns True to keep the consumer."""
        if spec.critical:
            policy = self.policy.critical_error
            if policy == CriticalErrorPolicy.RAISE:
                raise ConsumerDispatchError(spec.name, exc)
            if policy == CriticalErrorPolicy.CANCEL:
                logger.error(
                    "Critical consumer %r %s error (canceling): %s",
                    spec.name,
                    phase,
                    exc,
                )
                self._cancel_requested = True
                return False
            # CONTINUE
            logger.exception(
                "Critical consumer %r %s error (continuing):", spec.name, phase
            )
            return True
        else:
            nc_policy = self.policy.noncritical_error
            if nc_policy == NonCriticalErrorPolicy.DISCONNECT:
                logger.warning(
                    "Non-critical consumer %r disconnected on %s: %s",
                    spec.name,
                    phase,
                    exc,
                )
                return False
            # LOG
            logger.exception("Non-critical consumer %r %s error:", spec.name, phase)
            return True


# ───────────────────────── Adapters ─────────────────────────


def _call_with_fallback(cb: Any, *args: Any) -> int | None:
    """Call `cb` with progressively fewer positional args until it succeeds."""
    try:
        sig = inspect.signature(cb)
    except (TypeError, ValueError):
        cb(*args)
        return None

    for n in range(len(args), -1, -1):
        try:
            sig.bind(*args[:n])
        except TypeError:
            continue
        cb(*args[:n])
        return n
    return None


NULL = object()  # sentinel for "no args fit"


class _LegacyAdapter:
    """Wrap a legacy handler (with frameReady/sequenceStarted/sequenceFinished)."""

    def __init__(self, handler: Any) -> None:
        ss = getattr(handler, "sequenceStarted", None)
        self._seq_started = ss if callable(ss) else None

        fr = getattr(handler, "frameReady", None)
        self._frame_ready = fr if callable(fr) else None
        self._n_frame_args: int | None | object = NULL

        sf = getattr(handler, "sequenceFinished", None)
        self._seq_finished = sf if callable(sf) else None

    def setup(self, sequence: MDASequence, meta: dict[str, Any]) -> None:
        if self._seq_started:
            _call_with_fallback(self._seq_started, sequence, meta)

    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        if not self._frame_ready:
            return
        if (nf := self._n_frame_args) is not NULL:
            args = (img, event, meta)
            self._frame_ready(*args[:nf])  # type: ignore[misc]
        else:
            self._n_frame_args = _call_with_fallback(
                self._frame_ready, img, event, meta
            )

    def finish(self, sequence: MDASequence, status: RunStatus) -> None:
        if self._seq_finished:
            _call_with_fallback(self._seq_finished, sequence)


class _SignalRelay:
    """Relay frames to the runner's PMDASignaler.frameReady signal.

    NOTE: frame() is called from a worker thread, so all frameReady listeners
    must be thread-safe.
    """

    def __init__(self, signals: PMDASignaler) -> None:
        self._signals = signals

    def setup(self, sequence: MDASequence, meta: dict[str, Any]) -> None:
        pass

    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        self._signals.frameReady.emit(img, event, meta)

    def finish(self, sequence: MDASequence, status: RunStatus) -> None:
        if not type(self._signals).__name__ == "QMDASignaler":
            return

        # To preserve the pre-refactor guarantee that all frameReady slots have been
        # called before sequenceFinished is emitted, we flush pending events here. This
        # only applies when finish() runs on the main thread (i.e. when run() is called
        # directly); when run_mda() is used, the runner is already on a background
        # thread and Qt's ordering guarantees handle it.
        # (background details:)
        # frameReady is emitted from the _SignalRelay worker thread. With Qt,
        # cross-thread signal emissions are delivered as queued connections — they are
        # posted to the receiving thread's event queue and processed only on the next
        # event loop iteration.

        from qtpy.QtCore import QCoreApplication, QThread

        if (qapp := QCoreApplication.instance()) is not None:
            if QThread.currentThread() is qapp.thread():
                qapp.processEvents()
