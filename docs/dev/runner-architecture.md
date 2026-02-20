# MDA Runner Architecture

Visual overview of the consumer-based dispatch system introduced in `_runner.py`
and `_dispatch.py`. Each section below is a standalone Mermaid diagram.

---

## 1. System Architecture

High-level view: the runner thread produces frames, the dispatcher fans them out
to per-consumer worker threads, each with its own bounded queue.

```mermaid
graph TB
    subgraph User["User / Application"]
        API["mmc.mda.run(events,<br/>consumers=[...],<br/>policy=RunPolicy())"]
    end

    subgraph RunnerThread["Runner Thread"]
        direction TB
        PREP["_prepare_to_run()<br/><i>engine.setup_sequence()</i>"]
        DSTART["dispatcher.start()<br/><i>consumer.setup() for each</i>"]
        SIG_START(["sequenceStarted ⚡"])
        LOOP["Event Loop<br/><b>_run()</b>"]
        DCLOSE["dispatcher.close()<br/><i>drain queues, consumer.finish()</i>"]
        FINISH["_finish_run()<br/><i>engine.teardown_sequence()</i>"]
        SIG_FINISH(["sequenceFinished ⚡"])
        REPORT["return RunReport"]

        PREP --> DSTART --> SIG_START --> LOOP
        LOOP --> DCLOSE --> FINISH --> SIG_FINISH --> REPORT
    end

    subgraph EventLoop["Event Loop Detail"]
        direction TB
        WAIT["_wait_until_event()<br/><i>pause/cancel/timing</i>"]
        ENG_SETUP["engine.setup_event()"]
        ENG_EXEC["engine.exec_event()"]
        ITER["_iter_with_signals()<br/><i>generator.send(signal)</i>"]
        EMIT(["frameReady.emit() ⚡<br/><i>on runner thread</i>"])
        DISPATCH["dispatcher.submit(img, event, meta)"]
        CHECK{"dispatcher<br/>.should_cancel()?"}
        NEXT["next event"]

        WAIT --> ENG_SETUP --> ENG_EXEC --> ITER
        ITER --> EMIT --> DISPATCH --> CHECK
        CHECK -- no --> NEXT --> WAIT
        CHECK -- yes --> CANCEL["self._canceled = True"]
    end

    subgraph Dispatcher["FrameDispatcher"]
        direction TB
        FAN["submit() — fan-out"]

        subgraph Workers["Per-Consumer Worker Threads"]
            direction LR
            subgraph W1["Worker: tiff-writer"]
                Q1[("Queue<br/>maxsize=256<br/>(critical)")]
                T1["🧵 Thread"]
                C1["TiffWriter.frame()"]
                Q1 --> T1 --> C1
            end
            subgraph W2["Worker: display"]
                Q2[("Queue<br/>maxsize=256<br/>(observer)")]
                T2["🧵 Thread"]
                C2["LiveDisplay.frame()"]
                Q2 --> T2 --> C2
            end
            subgraph W3["Worker: metrics"]
                Q3[("Queue<br/>maxsize=256<br/>(observer)")]
                T3["🧵 Thread"]
                C3["Metrics.frame()"]
                Q3 --> T3 --> C3
            end
        end

        FAN --> Q1
        FAN --> Q2
        FAN --> Q3
    end

    API --> PREP
    DISPATCH --> FAN

    style RunnerThread fill:#1a1a2e,stroke:#16213e,color:#eee
    style Dispatcher fill:#0f3460,stroke:#16213e,color:#eee
    style EventLoop fill:#1a1a2e,stroke:#533483,color:#eee
    style Workers fill:#16213e,stroke:#0f3460,color:#eee
    style W1 fill:#1b4332,stroke:#2d6a4f,color:#eee
    style W2 fill:#3a2d5c,stroke:#533483,color:#eee
    style W3 fill:#3a2d5c,stroke:#533483,color:#eee
    style User fill:#2d2d2d,stroke:#555,color:#eee
```

---

## 2. Runner State Machine

States of the MDA runner during an acquisition.

```mermaid
stateDiagram-v2
    [*] --> Idle

    Idle --> Preparing : run() called
    Preparing --> Running : engine.setup_sequence()<br/>dispatcher.start()<br/>sequenceStarted ⚡

    state Running {
        [*] --> AwaitingEvent
        AwaitingEvent --> ExecutingEvent : min_start_time reached
        ExecutingEvent --> DispatchingFrame : engine yields (img, event, meta)
        DispatchingFrame --> ExecutingEvent : more frames from event
        DispatchingFrame --> AwaitingEvent : event done, next event
        ExecutingEvent --> AwaitingEvent : no output from event

        AwaitingEvent --> Paused : toggle_pause()
        Paused --> AwaitingEvent : toggle_pause()
        Paused --> Canceled : cancel()

        AwaitingEvent --> Canceled : cancel() or<br/>dispatcher.should_cancel()
        ExecutingEvent --> Canceled : generator.send("cancel")
        DispatchingFrame --> Canceled : dispatcher.should_cancel()
    }

    Running --> Closing : all events done /<br/>canceled / error
    Closing --> Finished : dispatcher.close()<br/><i>drains queues</i><br/><i>calls finish()</i>
    Finished --> Idle : _finish_run()<br/>sequenceFinished ⚡<br/>return RunReport

    note right of Closing
        dispatcher.close() blocks until
        all worker queues are drained
        and finish() is called on each consumer.
        This ensures all frames are delivered
        BEFORE sequenceFinished is emitted.
    end note

    note right of Running
        The cancel signal can originate from:
        1. User calling runner.cancel()
        2. A critical consumer requesting cancellation
        3. Both propagate through the same _canceled flag
    end note
```

---

## 3. Frame Dispatch Sequence

Timeline showing frame flow from engine through dispatcher to consumers.

```mermaid
sequenceDiagram
    participant U as User / GUI
    participant R as MDARunner<br/>(runner thread)
    participant E as MDAEngine
    participant D as FrameDispatcher
    participant W1 as Worker: writer<br/>(critical)
    participant W2 as Worker: display<br/>(non-critical)

    U->>R: run(events, consumers, policy)
    activate R

    R->>E: setup_sequence()
    E-->>R: SummaryMetaV1

    R->>D: start(sequence, meta)
    activate D
    D->>W1: consumer.setup()
    D->>W2: consumer.setup()
    D->>W1: thread.start()
    D->>W2: thread.start()
    deactivate D

    R-->>U: sequenceStarted ⚡

    loop for each MDAEvent
        R->>R: _wait_until_event()
        R-->>U: eventStarted ⚡
        R->>E: setup_event(event)
        R->>E: exec_event(event)

        loop for each frame yielded
            E-->>R: yield (img, event, meta)

            R-->>U: frameReady ⚡ (on runner thread)

            R->>D: submit(img, event, meta)
            D->>W1: queue.put(FrameMessage)
            D->>W2: queue.put(FrameMessage)

            Note over W1: dequeue → consumer.frame()
            Note over W2: dequeue → consumer.frame()

            R->>D: should_cancel()?
            D-->>R: false
        end

        R->>E: teardown_event(event)
    end

    R->>D: close(sequence, status)
    activate D
    D->>W1: queue.put(STOP)
    D->>W2: queue.put(STOP)
    Note over W1: drains remaining queue
    Note over W2: drains remaining queue
    D->>W1: consumer.finish()
    D->>W2: consumer.finish()
    D-->>R: RunReport
    deactivate D

    R->>E: teardown_sequence()
    R-->>U: sequenceFinished ⚡
    R-->>U: return RunReport
    deactivate R
```

---

## 4. Consumer Registration & Coercion

How different input types become `ConsumerSpec` instances in the dispatcher.

```mermaid
flowchart LR
    subgraph Inputs["run() parameters"]
        A["consumers=[<br/>  ConsumerSpec('w', writer),<br/>  ConsumerSpec('d', display),<br/>]"]
        B["output='data.ome.tiff'"]
        C["output=legacy_handler"]
    end

    subgraph Coercion["_coerce_outputs()"]
        B --> P{"Path or str?"}
        P -- yes --> HFP["handler_for_path()"]
        HFP --> FC{"FrameConsumer?"}
        FC -- yes --> CS1["ConsumerSpec(handler)"]
        FC -- no --> LA1["_LegacyAdapter(handler)<br/>→ ConsumerSpec"]

        C --> FC2{"FrameConsumer?"}
        FC2 -- yes --> CS2["ConsumerSpec(handler)"]
        FC2 -- no --> HAS{".frameReady?"}
        HAS -- yes --> LA2["_LegacyAdapter(handler)<br/>→ ConsumerSpec"]
        HAS -- no --> ERR["TypeError ✗"]
    end

    subgraph Result["FrameDispatcher"]
        A --> DISP["add_consumer() ×N"]
        CS1 --> DISP
        LA1 --> DISP
        CS2 --> DISP
        LA2 --> DISP
    end

    style Inputs fill:#1a1a2e,stroke:#333,color:#eee
    style Coercion fill:#2d2d2d,stroke:#555,color:#eee
    style Result fill:#0f3460,stroke:#16213e,color:#eee
```

---

## 5. Backpressure Policies

Decision tree when `dispatcher.submit()` finds a consumer's queue is full.

```mermaid
flowchart TD
    SUBMIT["dispatcher.submit(frame)"] --> WORKER["worker.submit(msg)"]
    WORKER --> FULL{"queue full?"}
    FULL -- no --> PUT["queue.put(msg) ✓"]

    FULL -- yes --> BP{"BackpressurePolicy?"}

    BP -- BLOCK --> WAIT["queue.put(msg)<br/><b>blocks runner thread</b><br/>until space available"]
    WAIT --> OK1["✓ frame enqueued"]

    BP -- DROP_NEWEST --> DISCARD["discard incoming frame<br/>report.dropped += 1"]
    DISCARD --> OK2["✓ runner continues<br/>(frame lost)"]

    BP -- DROP_OLDEST --> EVICT["queue.get_nowait()<br/><i>evict oldest frame</i><br/>report.dropped += 1"]
    EVICT --> RETRY["queue.put(msg)"]
    RETRY --> OK3["✓ newest frame kept"]

    BP -- FAIL --> RAISE["raise BufferError<br/>report.dropped += 1"]

    style WAIT fill:#1b4332,stroke:#2d6a4f,color:#eee
    style OK1 fill:#1b4332,stroke:#2d6a4f,color:#eee
    style DISCARD fill:#5c3a1e,stroke:#8b5e3c,color:#eee
    style OK2 fill:#5c3a1e,stroke:#8b5e3c,color:#eee
    style EVICT fill:#5c3a1e,stroke:#8b5e3c,color:#eee
    style OK3 fill:#5c3a1e,stroke:#8b5e3c,color:#eee
    style RAISE fill:#5c1a1a,stroke:#8b3a3a,color:#eee
```

---

## 6. Error Handling Policies

What happens when a consumer's `frame()` raises an exception.

```mermaid
flowchart TD
    ERR["consumer.frame() raises Exception"]
    ERR --> CRIT{"consumer.critical?"}

    CRIT -- yes --> CP{"CriticalErrorPolicy?"}
    CRIT -- no --> NP{"NonCriticalErrorPolicy?"}

    CP -- RAISE --> FATAL["Store ConsumerDispatchError<br/>worker.stop_requested = True<br/>worker stops processing"]
    FATAL --> CLOSE["On dispatcher.close():<br/><b>raise ConsumerDispatchError</b>"]

    CP -- CANCEL --> STOP["worker.stop_requested = True<br/>worker stops processing"]
    STOP --> SCAN["Runner sees should_cancel() → True<br/>sets self._canceled = True<br/><b>acquisition stops gracefully</b>"]

    CP -- CONTINUE --> LOG1["logger.exception()<br/><b>keep processing</b>"]

    NP -- LOG --> LOG2["logger.exception()<br/><b>keep processing</b>"]

    NP -- DISCONNECT --> DISC["worker.disconnected = True<br/>worker stops processing<br/><b>future submits skip this consumer</b>"]

    style FATAL fill:#5c1a1a,stroke:#8b3a3a,color:#eee
    style CLOSE fill:#5c1a1a,stroke:#8b3a3a,color:#eee
    style STOP fill:#5c3a1e,stroke:#8b5e3c,color:#eee
    style SCAN fill:#5c3a1e,stroke:#8b5e3c,color:#eee
    style DISC fill:#5c3a1e,stroke:#8b5e3c,color:#eee
    style LOG1 fill:#1b4332,stroke:#2d6a4f,color:#eee
    style LOG2 fill:#1b4332,stroke:#2d6a4f,color:#eee
```

---

## 7. Generator Signal Propagation

How `cancel`/`pause` signals flow from runner into the engine via
`generator.send()`, enabling mid-sequence hardware cancellation.

```mermaid
sequenceDiagram
    participant R as MDARunner
    participant I as _iter_with_signals()
    participant E as MDAEngine<br/>exec_event()
    participant S as _exec_single_camera<br/>_sequence()
    participant HW as Hardware<br/>(MMCore)

    R->>E: exec_event(event)
    E->>S: yield from _exec_single_camera_sequence()

    loop for each frame in hardware sequence
        HW-->>S: popNextImageAndMD()
        S-->>E: yield (img, event, meta)
        E-->>I: yield (img, event, meta)
        I-->>R: yield (img, event, meta)

        Note over R: Process frame,<br/>emit signals,<br/>dispatch to consumers

        alt user calls cancel()
            R->>I: (checks self._canceled)
            I->>E: gen.send("cancel")
            E->>S: gen.send("cancel")
            Note over S: status == "cancel"
            S->>HW: stopSequenceAcquisition()
            Note over S: return (generator ends)
        else user calls toggle_pause()
            R->>I: (checks self._paused)
            I->>E: gen.send("pause")
            E->>S: gen.send("pause")
            Note over S: status == "pause"<br/>log warning:<br/>"cannot pause HW sequence"
        else normal
            R->>I: (no flags set)
            I->>E: gen.send(None)
            E->>S: gen.send(None)
            Note over S: continue popping frames
        end
    end
```

---

## 8. Class Diagram

Key types and their relationships.

```mermaid
classDiagram
    class MDARunner {
        -PMDAEngine _engine
        -PMDASignaler _signals
        -bool _running
        -bool _paused
        -bool _canceled
        +run(events, output, consumers, policy) RunReport
        +cancel()
        +toggle_pause()
        +is_running() bool
        +is_paused() bool
        -_run(engine, events, dispatcher)
        -_iter_with_signals(iterable)
        -_coerce_outputs(output) list~ConsumerSpec~
        -_prepare_to_run(sequence)
        -_wait_until_event(event) bool
        -_finish_run(sequence)
    }

    class FrameDispatcher {
        +RunPolicy policy
        +float started_at
        -list~ConsumerSpec~ _specs
        -list~_ConsumerWorker~ _workers
        +add_consumer(spec)
        +start(sequence, meta)
        +submit(img, event, meta)
        +should_cancel() bool
        +queue_status() dict
        +close(sequence, status) RunReport
    }

    class _ConsumerWorker {
        +str name
        +bool critical
        +Queue queue
        +Thread thread
        +ConsumerReport report
        +ConsumerDispatchError fatal
        +Event stop_requested
        +Event disconnected
        +start()
        +submit(msg) bool
        +stop()
        +join(timeout)
        -_run()
        -_handle_error(exc)
        -_handle_critical_error(exc)
        -_handle_noncritical_error(exc)
    }

    class FrameConsumer {
        <<protocol>>
        +setup(sequence, meta)*
        +frame(img, event, meta)*
        +finish(sequence, status)*
    }

    class ConsumerSpec {
        <<dataclass>>
        +str name
        +FrameConsumer consumer
        +bool critical
    }

    class RunPolicy {
        <<dataclass>>
        +CriticalErrorPolicy critical_error
        +NonCriticalErrorPolicy noncritical_error
        +BackpressurePolicy backpressure
        +int critical_queue
        +int observer_queue
    }

    class RunReport {
        <<dataclass>>
        +RunStatus status
        +float started_at
        +float finished_at
        +tuple~ConsumerReport~ consumer_reports
    }

    class ConsumerReport {
        <<dataclass>>
        +str name
        +int submitted
        +int processed
        +int dropped
        +list~Exception~ errors
    }

    class _LegacyAdapter {
        -Any _handler
        +setup(sequence, meta)
        +frame(img, event, meta)
        +finish(sequence, status)
    }

    class _SignalRelay {
        -PMDASignaler _signals
        +setup(sequence, meta)
        +frame(img, event, meta)
        +finish(sequence, status)
    }

    class RunStatus {
        <<enum>>
        COMPLETED
        CANCELED
        FAILED
    }

    class CriticalErrorPolicy {
        <<enum>>
        RAISE
        CANCEL
        CONTINUE
    }

    class NonCriticalErrorPolicy {
        <<enum>>
        LOG
        DISCONNECT
    }

    class BackpressurePolicy {
        <<enum>>
        BLOCK
        DROP_OLDEST
        DROP_NEWEST
        FAIL
    }

    MDARunner "1" --> "1" FrameDispatcher : creates per run
    FrameDispatcher "1" --> "*" _ConsumerWorker : manages
    FrameDispatcher "1" --> "1" RunPolicy : configured by
    _ConsumerWorker "1" --> "1" ConsumerReport : tracks
    _ConsumerWorker ..> FrameConsumer : calls .frame()
    ConsumerSpec "1" --> "1" FrameConsumer : wraps
    FrameDispatcher --> RunReport : returns from close()
    RunReport "1" --> "*" ConsumerReport : contains
    RunPolicy --> CriticalErrorPolicy
    RunPolicy --> NonCriticalErrorPolicy
    RunPolicy --> BackpressurePolicy
    RunReport --> RunStatus
    _LegacyAdapter ..|> FrameConsumer : implements
    _SignalRelay ..|> FrameConsumer : implements
```

---

## 9. RunPolicy Configuration

Quick reference for the default `RunPolicy` and what each field controls.

```mermaid
mindmap
    root((RunPolicy))
        critical_error
            RAISE *default*
                Stop worker
                Store error
                Re-raise on close
            CANCEL
                Stop worker
                Runner sees should_cancel
                Graceful shutdown
            CONTINUE
                Log exception
                Keep processing
        noncritical_error
            LOG *default*
                Log exception
                Keep processing
            DISCONNECT
                Set disconnected flag
                Stop delivering frames
                Worker exits
        backpressure
            BLOCK *default*
                queue.put blocks
                Runner thread waits
                Zero frame loss
            DROP_NEWEST
                put_nowait fails
                Incoming frame discarded
                Runner never blocks
            DROP_OLDEST
                Evict oldest from queue
                Put newest frame
                Runner never blocks
            FAIL
                Raise BufferError
                Propagates to runner
        critical_queue
            256 default
            Queue size for critical consumers
        observer_queue
            256 default
            Queue size for non-critical consumers
```
