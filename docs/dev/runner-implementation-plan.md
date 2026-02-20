# MDA Runner Dispatch Refactor — Implementation Plan

## Goal

Replace the runner's signal-based frame dispatch (`mda_listeners_connected` +
`MDARelayThread` + unbounded deque) with an explicit `FrameDispatcher` that uses
per-consumer worker threads, bounded queues, backpressure policies, and
critical/non-critical consumer semantics. Also fold in `generator.send()`-based
cancel/pause propagation from runner to engine (PR #517).

The end result: the hot loop in `_run()` does one thing — `dispatcher.submit()` —
and everything else (threading, error handling, backpressure, signal relay) is
encapsulated in the dispatcher.

---

## New Module: `src/pymmcore_plus/mda/_dispatch.py`

All dispatch-related types and classes live here.

### Public Types

```python
class RunStatus(str, Enum):
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"
```

```python
@runtime_checkable
class FrameConsumer(Protocol):
    """Receives frames from the MDA runner."""

    def setup(self, sequence: MDASequence, meta: dict[str, Any]) -> None: ...
    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None: ...
    def finish(self, sequence: MDASequence, status: RunStatus) -> None: ...
```

Three methods. Criticality is NOT baked into method names — it's a property of
how the consumer is registered (on `ConsumerSpec`).

```python
@dataclass(slots=True)
class ConsumerSpec:
    name: str
    consumer: FrameConsumer
    critical: bool = True
```

### Policy Configuration

```python
class CriticalErrorPolicy(str, Enum):
    RAISE = "raise"        # propagate to caller after close()
    CANCEL = "cancel"      # stop acquisition, don't raise
    CONTINUE = "continue"  # log and continue

class NonCriticalErrorPolicy(str, Enum):
    LOG = "log"            # log error, keep consumer running
    DISCONNECT = "disconnect"  # stop delivering to this consumer

class BackpressurePolicy(str, Enum):
    BLOCK = "block"          # block runner until queue has space
    DROP_OLDEST = "drop_oldest"
    DROP_NEWEST = "drop_newest"
    FAIL = "fail"            # raise BufferError

@dataclass(slots=True)
class RunPolicy:
    critical_error: CriticalErrorPolicy = CriticalErrorPolicy.RAISE
    noncritical_error: NonCriticalErrorPolicy = NonCriticalErrorPolicy.LOG
    backpressure: BackpressurePolicy = BackpressurePolicy.BLOCK
    critical_queue: int = 256
    observer_queue: int = 256
```

### Diagnostics

```python
@dataclass(slots=True)
class ConsumerReport:
    name: str
    submitted: int = 0
    processed: int = 0
    dropped: int = 0
    errors: list[Exception] = field(default_factory=list)

@dataclass(slots=True)
class RunReport:
    status: RunStatus
    started_at: float
    finished_at: float
    consumer_reports: tuple[ConsumerReport, ...]
```

### Internal Classes

#### `_FrameMessage`

```python
@dataclass(slots=True)
class _FrameMessage:
    img: np.ndarray
    event: MDAEvent
    meta: dict[str, Any]
```

Single instance shared (by reference) across all consumer queues.

#### `_ConsumerWorker`

One per registered consumer. Owns a thread and a bounded queue.

```python
class _ConsumerWorker:
    _STOP = object()

    def __init__(self, spec: ConsumerSpec, policy: RunPolicy) -> None:
        self.name = spec.name
        self.callback = spec.consumer.frame
        self.critical = spec.critical
        self.policy = policy

        capacity = policy.critical_queue if spec.critical else policy.observer_queue
        self.queue: Queue[_FrameMessage | object] = Queue(maxsize=capacity)
        self.thread = threading.Thread(target=self._run, name=f"mda-{self.name}")

        self.report = ConsumerReport(name=self.name) if spec.critical else None
        self._fatal: ConsumerDispatchError | None = None
        self._stop_requested = threading.Event()
        self._disconnected = threading.Event()

    def start(self) -> None: ...
    def submit(self, msg: _FrameMessage) -> bool: ...
    def stop(self) -> None: ...
    def join(self) -> None: ...
    def _run(self) -> None: ...
```

`submit()` implements backpressure per policy. `_run()` is the thread loop that
pulls from the queue and calls `self.callback(msg.img, msg.event, msg.meta)`.
Error handling follows `critical_error` or `noncritical_error` policy.

The key error paths:
- **Non-critical + LOG**: `logger.exception(...)`, continue
- **Non-critical + DISCONNECT**: set `_disconnected`, return (thread exits)
- **Critical + CONTINUE**: append to `report.errors`, continue
- **Critical + CANCEL**: set `_stop_requested`, return (runner checks this)
- **Critical + RAISE**: set `_stop_requested` + store `_fatal`, return
  (dispatcher raises after `close()`)

#### `FrameDispatcher`

The single object the runner interacts with.

```python
class FrameDispatcher:
    def __init__(self, policy: RunPolicy | None = None) -> None:
        self.policy = policy or RunPolicy()
        self._specs: list[ConsumerSpec] = []
        self._workers: list[_ConsumerWorker] = []

    def add_consumer(self, spec: ConsumerSpec) -> None:
        """Register a consumer. Must be called before start()."""
        self._specs.append(spec)

    def start(self, sequence: MDASequence, meta: dict[str, Any]) -> None:
        """Call setup() on all consumers (synchronous), then start worker threads."""
        # For each spec, call consumer.setup(sequence, meta) synchronously.
        # If a critical consumer's setup() raises:
        #   - RAISE/CANCEL: don't include that consumer (or re-raise)
        #   - CONTINUE: include it anyway
        # If a non-critical consumer's setup() raises:
        #   - LOG: log, include it (frame delivery may still work)
        #   - DISCONNECT: exclude it entirely
        #
        # Create _ConsumerWorker for each surviving consumer.
        # Start all worker threads.

    def submit(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        """Fan out one frame to all workers. Called from runner hot loop."""
        msg = _FrameMessage(img, event, meta)
        for worker in self._workers:
            worker.submit(msg)

    def should_cancel(self) -> bool:
        """Check if any critical worker requested cancellation."""
        return any(w._stop_requested.is_set() for w in self._workers)

    def queue_status(self) -> dict[str, tuple[int, int]]:
        """Return {name: (pending, capacity)} per worker. For monitoring."""
        return {
            w.name: (w.queue.qsize(), w.queue.maxsize)
            for w in self._workers
        }

    def close(self, sequence: MDASequence, status: RunStatus) -> RunReport:
        """Stop workers, call finish() on all consumers, return report."""
        # Send _STOP to each worker, join all threads.
        # Call consumer.finish(sequence, status) synchronously for each spec.
        # (Same error handling as start() for finish callbacks.)
        # Collect ConsumerReports.
        # If any fatal error stored and policy is RAISE, raise it.
        # Return RunReport.
```

### Adapters

#### `_LegacyAdapter`

Wraps old-style handlers (`frameReady`/`sequenceStarted`/`sequenceFinished`) into
`FrameConsumer`:

```python
class _LegacyAdapter:
    """Wrap a legacy handler with frameReady() into a FrameConsumer."""

    def __init__(self, handler: Any) -> None:
        self._handler = handler

    def setup(self, sequence: MDASequence, meta: dict[str, Any]) -> None:
        cb = getattr(self._handler, "sequenceStarted", None)
        if callable(cb):
            _call_with_fallback(cb, sequence, meta)

    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        cb = getattr(self._handler, "frameReady", None)
        if callable(cb):
            _call_with_fallback(cb, img, event, meta)

    def finish(self, sequence: MDASequence, status: RunStatus) -> None:
        cb = getattr(self._handler, "sequenceFinished", None)
        if callable(cb):
            _call_with_fallback(cb, sequence)
```

Where `_call_with_fallback(cb, *args)` tries calling with all args, then
progressively fewer, to handle the 0-3 arg signature variants.

#### `_SignalRelay`

Internal non-critical consumer that keeps `events.frameReady` working:

```python
class _SignalRelay:
    """Relay frames to the runner's PMDASignaler.frameReady signal."""

    def __init__(self, signals: PMDASignaler) -> None:
        self._signals = signals

    def setup(self, sequence: MDASequence, meta: dict[str, Any]) -> None:
        pass

    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        self._signals.frameReady.emit(img, event, meta)

    def finish(self, sequence: MDASequence, status: RunStatus) -> None:
        pass
```

Registered as a non-critical consumer. This means `frameReady.emit()` happens
on the `_SignalRelay`'s worker thread, not the runner thread. This is consistent
with the current behavior (where it fires on the relay thread) and satisfies
tlambert03's feedback that the hot loop should only do `queue.put()`.

---

## Modified: `src/pymmcore_plus/mda/_runner.py`

### Changes to `MDARunner`

**Remove:**
- `_handlers: WeakSet` instance variable
- `_outputs_connected()` method
- `_handler_for_path()` method (move to `_dispatch.py` or keep in handlers)
- All imports of `mda_listeners_connected`, `_thread_relay`

**Add:**
- `_iter_with_signals()` method (from PR #517, for cancel/pause into generators)

**Modify `run()`:**

```python
def run(
    self,
    events: Iterable[MDAEvent],
    *,
    output: SingleOutput | Sequence[SingleOutput] | None = None,
    consumers: Sequence[ConsumerSpec] = (),
    policy: RunPolicy | None = None,
) -> RunReport:
    error = None
    sequence = events if isinstance(events, MDASequence) else GeneratorMDASequence()

    dispatcher = FrameDispatcher(policy)

    # Always add signal relay (non-critical, internal)
    dispatcher.add_consumer(ConsumerSpec(
        name="_signal_relay",
        consumer=_SignalRelay(self._signals),
        critical=False,
    ))

    # Add explicit consumers
    for spec in consumers:
        dispatcher.add_consumer(spec)

    # Coerce output parameter into ConsumerSpecs
    for spec in self._coerce_outputs(output):
        dispatcher.add_consumer(spec)

    status = RunStatus.COMPLETED
    try:
        engine = self._prepare_to_run(sequence)
        dispatcher.start(sequence, meta)
        self._signals.sequenceStarted.emit(sequence, meta)
        self._run(engine, events, dispatcher)
        if self._canceled:
            status = RunStatus.CANCELED
    except Exception as e:
        status = RunStatus.FAILED
        error = e
    finally:
        with exceptions_logged():
            self._finish_run(sequence)

    report = dispatcher.close(sequence, status)
    if error is not None:
        raise error
    return report
```

**Modify `_run()`:**

```python
def _run(
    self,
    engine: PMDAEngine,
    events: Iterable[MDAEvent],
    dispatcher: FrameDispatcher,
) -> None:
    teardown_event = getattr(engine, "teardown_event", lambda e: None)
    if isinstance(events, Iterator):
        event_iterator = iter
    else:
        event_iterator = getattr(engine, "event_iterator", iter)
    _events = event_iterator(events)

    self._reset_event_timer()
    self._sequence_t0 = self._t0

    for event in _events:
        if event.reset_event_timer:
            self._reset_event_timer()
        if self._wait_until_event(event) or not self._running:
            break

        self._signals.eventStarted.emit(event)
        logger.info("%s", event)
        engine.setup_event(event)

        try:
            runner_time_ms = self.seconds_elapsed() * 1000
            event.metadata["runner_t0"] = self._sequence_t0
            output = engine.exec_event(event) or ()

            for payload in self._iter_with_signals(output):
                img, ev, meta = payload
                ev.metadata.pop("runner_t0", None)
                if "runner_time_ms" not in meta:
                    meta["runner_time_ms"] = runner_time_ms

                # THE HOT PATH: one call, everything else is in the dispatcher
                dispatcher.submit(img, ev, meta)

                if dispatcher.should_cancel():
                    self._canceled = True
                    break
        finally:
            teardown_event(event)

        if self._canceled:
            break
```

**New `_coerce_outputs()`:**

```python
def _coerce_outputs(
    self, output: SingleOutput | Sequence[SingleOutput] | None
) -> list[ConsumerSpec]:
    if output is None:
        return []

    if isinstance(output, (str, Path)) or not isinstance(output, Sequence):
        items = [output]
    else:
        items = list(output)

    specs: list[ConsumerSpec] = []
    for i, item in enumerate(items):
        if isinstance(item, (str, Path)):
            handler = handler_for_path(item)
            # New-style handlers (from ome-writers) implement FrameConsumer
            if isinstance(handler, FrameConsumer):
                specs.append(ConsumerSpec(f"output-{i}", handler, critical=True))
            else:
                # Legacy handler with frameReady()
                specs.append(ConsumerSpec(
                    f"output-{i}", _LegacyAdapter(handler), critical=True,
                ))
        elif isinstance(item, FrameConsumer):
            specs.append(ConsumerSpec(f"output-{i}", item, critical=True))
        elif callable(getattr(item, "frameReady", None)):
            specs.append(ConsumerSpec(
                f"output-{i}", _LegacyAdapter(item), critical=True,
            ))
        else:
            raise TypeError(f"Invalid output: {item!r}")

    return specs
```

**New `_iter_with_signals()` (from PR #517):**

```python
def _iter_with_signals(self, iterable: Iterable) -> Iterator:
    """Wrap engine output, sending cancel/pause signals via generator.send()."""
    gen = iter(iterable)
    is_generator = hasattr(gen, "send")
    try:
        item = next(gen)
        while True:
            yield item
            signal = None
            if self._canceled:
                signal = "cancel"
            elif self._paused:
                signal = "pause"
            item = gen.send(signal) if is_generator else next(gen)
    except StopIteration:
        pass
```

**`_prepare_to_run()` changes:**

Returns the summary metadata dict (needed by dispatcher.start):

```python
def _prepare_to_run(self, sequence: MDASequence) -> tuple[PMDAEngine, dict]:
    if not self._engine:
        raise RuntimeError("No MDAEngine set.")
    self._running = True
    self._paused = False
    self._paused_time = 0.0
    self._canceled = False
    self._sequence = sequence
    meta = self._engine.setup_sequence(sequence) or {}
    return self._engine, meta
```

**`_finish_run()` stays mostly the same** — it just handles engine teardown and
sets `_running = False`. Signal emission for `sequenceFinished` happens here
(not in the dispatcher, since it's a runner-level concern):

```python
def _finish_run(self, sequence: MDASequence) -> None:
    self._running = False
    self._canceled = False
    if hasattr(self._engine, "teardown_sequence"):
        self._engine.teardown_sequence(sequence)
    logger.info("MDA Finished: %s", sequence)
    self._signals.sequenceFinished.emit(sequence)
```

### `get_output_handlers()` removal or deprecation

The current `get_output_handlers()` returns the WeakSet contents. With the
dispatcher model, this doesn't map cleanly. Options:
- Remove it (breaking change)
- Deprecate with a warning
- Expose `dispatcher.queue_status()` as the replacement

Recommend: deprecate with a warning pointing to the `RunReport` returned by `run()`.

---

## Modified: `src/pymmcore_plus/mda/_engine.py`

### `exec_sequenced_event` — generator.send() support

The sequenced event execution methods become generators that receive signals:

```python
# In the inner loop that polls the circular buffer:
signal = yield ImagePayload(image, event, meta)
if signal == "cancel":
    core.stopSequenceAcquisition()
    return
if signal == "pause":
    logger.warning("Cannot pause hardware sequence; only cancel is supported.")
```

This is backward compatible: if the runner iterates with plain `next()` (old
behavior), `signal` is `None` and nothing changes. The new runner uses
`_iter_with_signals()` which calls `gen.send(signal)`.

Only `exec_sequenced_event` (and its multi-camera variant) need this change —
single-event execution already returns after one yield, so there's no loop to
cancel mid-way.

---

## Exports

In `src/pymmcore_plus/mda/__init__.py`, export:

```python
from ._dispatch import (
    BackpressurePolicy,
    ConsumerReport,
    ConsumerSpec,
    CriticalErrorPolicy,
    FrameConsumer,
    FrameDispatcher,
    NonCriticalErrorPolicy,
    RunPolicy,
    RunReport,
    RunStatus,
)
```

---

## Backward Compatibility

| Current API | After refactor |
|---|---|
| `run(events, output=...)` | Works unchanged. `output` coerced to `ConsumerSpec`s internally. |
| `events.frameReady` signal | Still fires, via `_SignalRelay` non-critical consumer. Now emits on worker thread (same as current relay thread behavior). |
| `events.sequenceStarted` | Still emitted by runner in `run()`. |
| `events.sequenceFinished` | Still emitted by runner in `_finish_run()`. |
| Legacy handlers with `frameReady()` | Wrapped by `_LegacyAdapter` automatically. |
| `mda_listeners_connected` | Still importable, but runner no longer uses it. Can be deprecated later. |
| `get_output_handlers()` | Deprecate with warning. |

**New capabilities:**
- `run(..., consumers=[...])` — explicit consumer registration
- `run(..., policy=RunPolicy(...))` — configure error/backpressure behavior
- `run()` returns `RunReport` — diagnostics (previously returned `None`)
- `dispatcher.queue_status()` — live backpressure monitoring

---

## Implementation Order

### Phase 1: `_dispatch.py` — the dispatcher in isolation

Create the module with all types and classes. Write tests that exercise the
dispatcher directly (without a real runner or engine):

- Feed it mock frames, verify consumers receive them
- Test critical consumer failure → `should_cancel()` returns True
- Test non-critical consumer failure → logged/disconnected, run continues
- Test backpressure policies (BLOCK, DROP_OLDEST, DROP_NEWEST, FAIL)
- Test `queue_status()` returns correct values
- Test `RunReport` correctness
- Test `_LegacyAdapter` with 0/1/2/3-arg handlers
- Test `_SignalRelay` emits signals

### Phase 2: Integrate into `_runner.py`

Modify MDARunner to use FrameDispatcher. Adapt existing MDA tests to work
with the new internals. Key tests:

- `run(events, output="path.zarr")` still writes correctly
- `run(events, output=legacy_handler)` still works
- `run(events, consumers=[...])` with new-style consumers
- Cancel mid-run → consumers receive `finish(status=CANCELED)`
- Consumer error → acquisition stops (critical) or continues (non-critical)
- `RunReport` returned with correct stats

### Phase 3: `_engine.py` — generator.send() for cancel

Add `generator.send()` support to `exec_sequenced_event`. Tests:

- Cancel during hardware sequence → `stopSequenceAcquisition()` called
- Pause during hardware sequence → warning logged
- Non-generator engines → no change in behavior

### Phase 4: Cleanup

- Deprecate `get_output_handlers()` with warning
- Remove `_v2.py` (experimental code absorbed into main runner)
- Update `__init__.py` exports
- Update any documentation referencing the old dispatch mechanism

---

## What This Plan Does NOT Cover

- **Changing `sequenceFinished` signal signature** (adding RunStatus, accumulated
  metadata per PR #502). This can be a follow-up — it's a signal API change
  that deserves its own consideration.
- **OMERunnerHandler / ome-writers integration** (PRs #501, #545). That's a
  separate concern about a specific sink implementation. Once this dispatch
  refactor lands, new sinks just implement `FrameConsumer` — three methods.
- **Handler-level async** (e.g., OMERunnerHandler's internal writer thread from
  #545). With per-consumer worker threads in the dispatcher, handlers don't need
  their own internal threads — the dispatcher already decouples acquisition from
  consumption. Handlers can be synchronous.
