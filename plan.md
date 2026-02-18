 Here is Claude's plan:
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Plan: Unify Handler Dispatch and Move Threading into MDARunner

 Context

 Currently the MDA runner has two separate handler systems:
 1. BaseRunnerHandler instances (e.g. OMERunnerHandler) - called directly via _runner_handler_group with
 prepare()/writeframe()/cleanup()
 2. SupportsFrameReady instances (e.g. ImageSequenceWriter) - connected via signals through mda_listeners_connected, which
 spawns its own MDARelayThread

 Additionally, OMERunnerHandler has its own internal threading (queue + writer thread) for async writes. This results in
 duplicated threading logic in multiple places.

 Goal: Centralize all handler dispatching inside the runner on a single background thread, unify the handler list, and
 simplify OMERunnerHandler to be purely synchronous.

 ---
 Changes

 1. Add _HandlerDispatchThread class to _runner.py

 New internal class that owns:
 - A flat list of all handlers (both types)
 - A queue.Queue for message passing
 - A daemon threading.Thread that drains the queue

 Message types: ("prepare", seq, meta), ("frame", img, event, meta), ("cleanup", seq), _STOP sentinel.

 Type-based dispatch inside the thread:
 - BaseRunnerHandler -> prepare() / writeframe() / cleanup()
 - SupportsFrameReady -> sequenceStarted() / frameReady() / sequenceFinished() (if method exists)

 Cache inspect.signature parameter counts for frameReady at handler registration time (supports 0-3 arg signatures).

 Error propagation: store exception in _error, check before each enqueue and in stop_and_join().

 2. Refactor MDARunner

 - __init__: Replace self._handlers (WeakSet) and self._runner_handler_group (OMERunnerHandlerGroup) with self._dispatch =
 _HandlerDispatchThread()
 - _outputs_connected: Change to a simple @contextmanager that calls self._dispatch.set_handlers(...) /
 self._dispatch.clear(). Remove mda_listeners_connected usage.
 - _prepare_to_run: Start dispatch thread, enqueue prepare, then emit sequenceStarted signal
 - _run: Replace self._runner_handler_group.writeframe(...) with self._dispatch.enqueue_frame(...). Keep
 self._signals.frameReady.emit(...) for external listeners.
 - _finish_run: Enqueue cleanup, call self._dispatch.stop_and_join(), then emit sequenceFinished signal
 - get_output_handlers: Return tuple(self._dispatch)

 3. Simplify OMERunnerHandler

 Remove all internal threading: _asynchronous, _queue, _writer_thread, _write_error, _enqueue_frame(), _drain_queue().

 - prepare(): Same setup logic, but no thread start
 - writeframe(): Always calls _write_frame() directly (synchronous)
 - cleanup(): Just closes the stream (no thread join/queue drain)

 4. Deprecate StreamSettings fields

 In _base_runner_handler.py, add __post_init__ deprecation warning for asynchronous and queue_maxsize if set to non-default
  values. Keep fields for one release cycle.

 5. Remove OMERunnerHandlerGroup

 Delete from _runner_handler.py. It's internal-only (not in __all__).

 6. Keep mda_listeners_connected as public API

 _thread_relay.py stays unchanged. It remains available for external users who want to connect handlers to MDA signals
 outside of output=. The runner just no longer uses it internally.

 7. Update tests

 - Remove async/queue tests from test_runner_handler.py (those test OMERunnerHandler's internal threading which is removed)
 - Update fixtures to remove asynchronous=False settings
 - Existing test_thread_relay.py and test_mda.py should still pass since signals are still emitted

 ---
 Files to Modify

 ┌────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────┐
 │                          File                          │                         Change                          │
 ├────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
 │ src/pymmcore_plus/mda/_runner.py                       │ Add _HandlerDispatchThread, refactor MDARunner          │
 ├────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
 │ src/pymmcore_plus/mda/handlers/_runner_handler.py      │ Simplify OMERunnerHandler, remove OMERunnerHandlerGroup │
 ├────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
 │ src/pymmcore_plus/mda/handlers/_base_runner_handler.py │ Deprecate StreamSettings.asynchronous/queue_maxsize     │
 ├────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
 │ tests/io/test_runner_handler.py                        │ Remove internal-threading tests, update fixtures        │
 └────────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────┘

 Verification

 1. Run pytest tests/test_mda.py - core MDA flow with unified dispatch
 2. Run pytest tests/io/test_runner_handler.py - OMERunnerHandler without internal threading
 3. Run pytest tests/test_thread_relay.py - public API still works
 4. Run pytest tests/io/test_image_sequence_writer.py - ImageSequenceWriter as SupportsFrameReady through dispatch thread