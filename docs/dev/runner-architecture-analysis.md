# MDA Runner Data Pipeline: Architecture Analysis

> Analysis date: 2026-02-20
> Branch context: `runnerv2`
> Related PRs: #501, #502, #517, #545, #551
> Related local experiments: `src/pymmcore_plus/mda/_v2.py`

## Current Architecture (v1)

The MDA runner (`_runner.py`) sits between the engine (which produces frames) and
consumers (which receive them). The data flow today:

```
Engine.exec_event() yields (img, event, meta)
    |
MDARunner._run() loop
    |
frameReady.emit(img, event, meta)          # synchronous signal on runner thread
    |
MDARelayThread (via mda_listeners_connected)
    |  appends to unbounded deque
    |  polls at 5ms intervals
    |
relay.signals.frameReady.emit(...)         # on relay thread
    |
Handler.frameReady(img, event, meta)       # e.g. OMEZarrWriter, TensorStoreHandler
```

### Key files

| File | Role |
|------|------|
| `mda/_runner.py` | MDARunner — event loop, timing, pause/cancel |
| `mda/_engine.py` | MDAEngine — hardware control, yields `(img, event, meta)` |
| `mda/_protocol.py` | PMDAEngine protocol |
| `mda/_thread_relay.py` | MDARelayThread + `mda_listeners_connected` context manager |
| `mda/events/_protocol.py` | PMDASignaler — signal definitions |
| `mda/events/_psygnal.py` | psygnal-based signal implementation |
| `mda/events/_qsignals.py` | Qt-based signal implementation |
| `mda/handlers/` | OMEZarrWriter, OMETiffWriter, TensorStoreHandler, etc. |
| `core/_mmcore_plus.py` | `CMMCorePlus.run_mda()` — spawns thread, calls `mda.run()` |

### How handlers are wired up today

`MDARunner.run()` calls `_outputs_connected(output)`, which:
1. Converts path strings to handler objects via `handler_for_path()`
2. Enters the `mda_listeners_connected()` context manager
3. That creates an `MDARelayThread` which:
   - Connects to runner signals (sequenceStarted, frameReady, etc.)
   - Appends events to an unbounded deque
   - Polls from a background thread, re-emitting to handler methods

Handlers are held in a `WeakSet` and matched by method name (`frameReady`,
`sequenceStarted`, `sequenceFinished`).

---

## Problems With the Current Architecture

### 1. No sink vs. observer distinction

All consumers are treated identically. If a Zarr writer fails (disk full, I/O
error), the acquisition continues unaware — data is silently lost. A live
viewer failing should be non-fatal; a data writer failing should halt the run.

### 2. No error propagation

`frameReady.emit()` is fire-and-forget. Exceptions in handlers are swallowed by
the signal mechanism. The runner has no way to learn about failures mid-loop.

### 3. No backpressure

The `MDARelayThread` uses an unbounded `collections.deque`. If handlers are
slower than acquisition, the deque grows without limit. There is no mechanism to
block, drop, or fail when consumers can't keep up.

### 4. Implicit handler lifecycle

Handlers are wired up via `mda_listeners_connected`, which matches method names
to signal names. This is clever but obscure. There's no explicit
prepare/write/cleanup lifecycle — handlers must infer state from signal ordering.

### 5. No run diagnostics

When a sequence finishes, nobody knows how it ended (completed? canceled?
errored?) or what happened during it (frames dropped? handlers failed?).
`sequenceFinished` only emits the `MDASequence` object.

### 6. Cannot cancel/pause into sequenced events

During hardware-triggered sequences, the engine runs a long inner loop. The
runner is stuck waiting for the next `yield` and cannot check for cancellation.

---

## PR-by-PR Summary

### PR #501 — OME-Writers Handler (WIP, Open)

**What:** Adds `OMEWriterHandler` wrapping the `ome-writers` library. Follows the
existing signal-based handler protocol (`sequenceStarted`/`frameReady`/`sequenceFinished`).

**Relevance to runner architecture:** Low — this is about a specific sink
implementation, not the dispatch pipeline. However, it demonstrates the need for
a cleaner handler lifecycle: the handler needs summary metadata at start time to
configure dimensions, and needs to know completion status at finish time.

**Status:** WIP, dormant since 2025-09-11.

### PR #502 — Store Metadata in Runner, Update sequenceFinished (Open)

**What:** Runner accumulates frame metadata centrally. Enhanced `sequenceFinished`
signal to include `RunStatus`, summary metadata, and all frame metadata.

**Key changes:**
- `RunStatus` enum: `IDLE`, `RUNNING`, `PAUSED`, `CANCELED`, `ERROR`, `COMPLETED`
- `sequenceFinished.emit(sequence, status, summary_meta, frame_metas)`
- `_canceled` renamed to `_request_cancel`
- `__slots__` added to MDARunner

**Relevance:** Addresses challenge #5 (diagnostics) and partially #4 (lifecycle).
Handlers no longer need to independently track metadata. However, this is still
signal-based — it doesn't address error propagation or backpressure.

**Design tension noted by author:** The metadata types (`SummaryMetaV1`,
`FrameMetaV1`) are engine-specific, but the runner emits them. The protocol
declares `Mapping` but the docs reference specific schemas.

**Status:** Open, periodically rebased, not merged. Superseded in scope by later PRs.

### PR #517 — Cancel Sequenced Events via generator.send() (Open, Conflicting)

**What:** Enables cancel/pause communication from runner to engine during
hardware-triggered sequences using Python's `generator.send()` mechanism.

**Key changes:**
- Engine's `exec_sequenced_event` becomes a generator that receives signals
  via `send()`: `signal = yield payload`
- Runner wraps iteration with `_iter_with_signals()` that sends `"cancel"` or
  `"pause"` strings
- Backward-compatible: plain iterables work unchanged

**Architectural principle:** Engine never imports or references the runner. All
communication flows through the iteration protocol. This was a key design
decision by tlambert03 after rejecting an earlier version where the engine
reached into runner state.

**Relevance:** Addresses challenge #6. Orthogonal to data dispatch — composable
with any pipeline architecture.

**Limitation:** Pause cannot actually pause hardware sequences; only cancel
(via `core.stopSequenceAcquisition()`) is actionable.

**Status:** Open with merge conflicts. Core approach agreed upon.

### PR #545 — Runner Handlers Without Signals (Open)

**What:** Introduces `BaseRunnerHandler` protocol with explicit lifecycle:
`prepare(sequence, meta)` / `writeframe(frame, event, meta)` / `cleanup()`.
Runner directly manages handler calls instead of going through signals.

**Key changes:**
- `BaseRunnerHandler` protocol (runtime-checkable)
- `OMERunnerHandler` — concrete implementation wrapping `ome-writers`
- `OMERunnerHandlerGroup` — composite pattern for multiple handlers
- Path-based outputs (`"output.zarr"`) now go through runner-managed pathway
- Signal-based handlers (`frameReady`) still coexist for legacy support
- Dependency shift: `ome-writers` replaces direct `tensorstore` dependency

**Runner flow with both pathways:**
```
_prepare_to_run()
  -> engine.setup_sequence()
  -> runner_handler_group.prepare()    # NEW: opens streams
  -> signals.sequenceStarted.emit()

_run() loop
  -> runner_handler_group.writeframe() # NEW: errors propagate
  -> signals.frameReady.emit()         # legacy: fire-and-forget

_finish_run()
  -> runner_handler_group.cleanup()    # NEW: drains, closes
  -> signals.sequenceFinished.emit()
```

**Key review feedback from tlambert03:**
- Don't add a new `writer` parameter — keep `output` and change internals
- Use a Protocol in type aliases, not concrete classes
- Don't subclass `ome_writers.AcquisitionSettings`

**Relevance:** Addresses challenges #2 (error propagation) and #4 (lifecycle).
Partial on #1 (sinks get error propagation, but no formal observer category).

**Status:** Open, feedback addressed, awaiting further review.

### PR #551 — Unified _HandlersThread (Open, builds on #545)

**What:** Single background thread for ALL handler dispatch (both
`BaseRunnerHandler` and `SupportsFrameReady`). Replaces `mda_listeners_connected`
and `MDARelayThread`.

**Key changes:**
- `_HandlersThread` class with queue-based producer/consumer pattern
- Lifecycle methods (`prepare`/`cleanup`) synchronous on runner thread
- Frame dispatch (`writeframe`/`frameReady`) async on background thread
- Errors captured in background thread, re-raised on runner thread
- `_STOP` sentinel for clean shutdown

**Key review feedback from tlambert03:**
- `frameReady.emit()` should also move into the background thread (the only
  thing in the hot loop should be `queue.put()`)
- Lifecycle methods correctly stay synchronous: "setup/prepare/teardown/finished...
  that all should be blocking main thread stuff"

**Relevance:** Addresses challenges #2, #3 (partially — single bounded queue),
and #4. However, single dispatch thread means one slow handler affects all others.

**Status:** Open, tests passing, awaiting further review. Blocked on #545.

---

## Local Experiment: `_v2.py` (MDARunnerV2)

The most comprehensive attempt. Key components:

### FrameConsumer Protocol

```python
class FrameConsumer(Protocol):
    # Critical callbacks — errors can halt acquisition
    def setup_sequence(self, sequence, summary_meta) -> None: ...
    def receive_frame(self, frame, event, meta) -> None: ...
    def finish_sequence(self, sequence, status) -> None: ...

    # Non-critical callbacks — errors logged/disconnected
    def on_start(self, sequence, summary_meta) -> None: ...
    def on_frame(self, frame, event, meta) -> None: ...
    def on_finish(self, sequence, status) -> None: ...
```

Criticality is encoded in method names: `receive_frame` = critical,
`on_frame` = non-critical. A consumer can implement both.

### RunPolicy

```python
@dataclass
class RunPolicy:
    critical_error: CriticalErrorPolicy = CriticalErrorPolicy.RAISE
    noncritical_error: NonCriticalErrorPolicy = NonCriticalErrorPolicy.LOG
    max_queue: int = 256
    backpressure: BackpressurePolicy = BackpressurePolicy.BLOCK
    observer_queue: int = 256
```

Error policies: `RAISE` / `CANCEL` / `CONTINUE` for critical;
`LOG` / `DISCONNECT` for non-critical.

Backpressure policies: `BLOCK` / `DROP_OLDEST` / `DROP_NEWEST` / `FAIL`.

### FrameDispatcher

Per-consumer worker threads with bounded queues:

```
dispatcher.submit(img, event, meta)
    |
    +--> [Critical Worker 1] --Queue(256)--> sink.receive_frame()
    +--> [Critical Worker 2] --Queue(256)--> sink.receive_frame()
    +--> [Observer Worker 1] --Queue(256)--> viewer.on_frame()
    +--> [Observer Worker 2] --Queue(256)--> viewer.on_frame()
```

- Lifecycle callbacks (`setup_sequence`, `finish_sequence`) run synchronously
- Frame callbacks (`receive_frame`, `on_frame`) run on per-consumer threads
- Critical workers track stats and can request cancellation
- Non-critical workers use separate queue sizes

### RunReport

```python
@dataclass
class RunReport:
    status: RunStatus          # COMPLETED, CANCELED, FAILED
    started_at: float
    finished_at: float
    consumer_reports: tuple[ConsumerReport, ...]

@dataclass
class ConsumerReport:
    name: str
    submitted: int
    processed: int
    dropped: int
    errors: list[Exception]
```

### Legacy Adapter

`_LegacyOutputAdapter` wraps old-style handlers (with `frameReady`,
`sequenceStarted`, `sequenceFinished`) into the `FrameConsumer` interface.
Uses try/except fallback chains for variable-signature handlers.

### Signal Relay

`_FrameReadySignalConsumer` is an internal non-critical consumer that relays
frames to `events.frameReady.emit()`, maintaining backward compatibility with
code that connects to the signal directly.

---

## Challenges Summary

| # | Challenge | Which PRs/experiments address it |
|---|-----------|----------------------------------|
| 1 | Sink vs. observer semantics | `_v2.py` (fully), #545/#551 (partially) |
| 2 | Error propagation from consumers | `_v2.py`, #545, #551 |
| 3 | Backpressure / bounded queues | `_v2.py` (fully), #551 (partially) |
| 4 | Explicit handler lifecycle | `_v2.py`, #545, #551 |
| 5 | Run diagnostics & status | `_v2.py` (RunReport), #502 (RunStatus) |
| 6 | Cancel/pause into sequenced events | #517 (generator.send()) |

---

## Canonical Design Patterns

The problems map to well-known patterns:

1. **Staged Event-Driven Architecture (SEDA):** Each stage (acquisition,
   dispatch, writing) connected by bounded queues with explicit admission
   control. This is what `_v2.py`'s `_ConsumerWorker` + `BackpressurePolicy`
   implements.

2. **Prioritized Publish-Subscribe:** Subscribers have criticality levels.
   Critical subscribers can block or cancel the publisher; non-critical
   subscribers are best-effort. The `_v2.py` naming convention encodes this.

3. **Circuit Breaker:** If a critical consumer fails, the acquisition circuit
   "breaks." `CriticalErrorPolicy.CANCEL` is this pattern.

4. **Adapter:** `_LegacyOutputAdapter` wraps old `frameReady` handlers into the
   new `FrameConsumer` interface for gradual migration.

---

## Architecture Options

### Option A: Refined `_v2.py` — Per-Consumer Worker Threads

The `_v2.py` approach with refinements:

```
Engine.exec_event() yields (img, event, meta)
    |
Runner hot loop: dispatcher.submit(img, event, meta)
    |
    +--> [Critical Worker 1] --Queue(bounded)--> sink.receive_frame()
    +--> [Critical Worker 2] --Queue(bounded)--> sink.receive_frame()
    +--> [Observer Worker 1] --Queue(bounded)--> viewer.on_frame()
    +--> [Observer Worker 2] --Queue(bounded)--> viewer.on_frame()
```

**Lifecycle** (synchronous, on runner thread):
- `dispatcher.start()` -> calls `setup_sequence()` / `on_start()`
- `dispatcher.close()` -> drains queues, calls `finish_sequence()` / `on_finish()`,
  returns `RunReport`

**Error handling:**
- Critical worker fails -> sets `stop_requested` -> runner checks
  `dispatcher.should_cancel()` -> breaks loop
- Non-critical worker fails -> logged or disconnected per policy

**Strengths:**
- Maximum consumer isolation (slow Zarr writer doesn't starve TIFF writer)
- Per-consumer backpressure and bounded queues
- Rich diagnostics via RunReport
- Backward compatible via legacy adapter

**Weaknesses:**
- Thread-per-consumer is heavyweight for many consumers
- The dual naming convention (`receive_frame` vs `on_frame`) on a single
  protocol is confusing — criticality should arguably be a registration-time
  property, not baked into method names

**Suggested refinement:** Make criticality a property of `ConsumerSpec`, not the
method name. One protocol with 3 methods (`setup`/`frame`/`finish`), and the
spec says `critical=True|False`:

```python
class FrameConsumer(Protocol):
    def setup(self, sequence: MDASequence, meta: dict) -> None: ...
    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict) -> None: ...
    def finish(self, sequence: MDASequence, status: RunStatus) -> None: ...

@dataclass
class ConsumerSpec:
    name: str
    consumer: FrameConsumer
    critical: bool = True
```

### Option B: Single Dispatch Thread + Synchronous Critical Path

Simpler, inspired by #551:

```
Engine.exec_event() yields (img, event, meta)
    |
Runner hot loop:
    +-- critical_sink.writeframe(img, event, meta)   # synchronous
    +-- dispatch_queue.put(img, event, meta)          # async for non-critical
            |
       [Single Dispatch Thread]
            +--> observer_1.on_frame()
            +--> observer_2.on_frame()
            +--> events.frameReady.emit()
```

**Strengths:** Simpler, one background thread, critical sinks get immediate
error propagation.

**Weaknesses:** Critical sinks block the acquisition loop (if writing is slow,
acquisition slows). All non-critical observers share one thread. Less diagnostic
granularity.

### Recommendation

**Option A (refined `_v2.py`)** is the stronger architecture:

1. Critical sinks that do I/O need their own thread — a slow TIFF write
   shouldn't block the camera's circular buffer.
2. Bounded queues with backpressure are essential for long acquisitions.
3. RunReport is genuinely useful for debugging.
4. The `generator.send()` mechanism from PR #517 should be folded in for
   runner-to-engine communication — it's orthogonal and composable.

The main simplification: use 3-method protocol + `critical` flag on
`ConsumerSpec` instead of the 6-method protocol with name-encoded semantics.

---

## Additional Considerations

### Metadata accumulation (from PR #502)

The runner should accumulate frame metadata centrally and pass it (along with
`RunStatus`) to `finish()` callbacks and `sequenceFinished` signal. This
eliminates duplicated tracking across consumers.

### Signal relay

`events.frameReady` should still fire for backward compatibility, but as an
internal non-critical consumer managed by the dispatcher — not as a separate
mechanism. This is what `_v2.py`'s `_FrameReadySignalConsumer` does.

### Threading model for frameReady.emit()

Per tlambert03's feedback on #551: ideally the *only* thing in the hot loop is
`queue.put()`. All signal emission should happen on the dispatch thread, not the
runner thread. This maximizes acquisition throughput but may break consumers
that expect signals on the runner thread.

### handler_for_path()

Path-based outputs should produce consumers directly (not go through the legacy
signal pathway). PR #545's approach of returning `OMERunnerHandler` for
`.zarr`/`.tiff` paths is correct.
