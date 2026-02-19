from __future__ import annotations

import inspect
import queue
import threading
import time
import warnings
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple
from unittest.mock import MagicMock

from useq import MDASequence

from pymmcore_plus._logger import exceptions_logged, logger

from ._protocol import PMDAEngine
from .events import PMDASignaler, _get_auto_MDA_callback_class
from .handlers._base_runner_handler import BaseRunnerHandler

if TYPE_CHECKING:
    from typing import Protocol, TypeAlias

    import numpy as np
    from useq import MDAEvent

    from pymmcore_plus.mda.handlers._img_sequence_writer import ImageSequenceWriter
    from pymmcore_plus.metadata.schema import FrameMetaV1, SummaryMetaV1

    from ._engine import MDAEngine

    class FrameReady0(Protocol):
        """Data handler with a no-argument `frameReady` method."""

        def frameReady(self) -> Any: ...

    class FrameReady1(Protocol):
        """Data handler with a `frameReady` method that takes `(image,)` ."""

        def frameReady(self, img: np.ndarray, /) -> Any: ...

    class FrameReady2(Protocol):
        """Data handler with a `frameReady` method that takes `(image, event)`."""

        def frameReady(self, img: np.ndarray, event: MDAEvent, /) -> Any: ...

    class FrameReady3(Protocol):
        """Data handler with a `frameReady` method that takes `(image, event, meta)`."""

        def frameReady(
            self, img: np.ndarray, event: MDAEvent, meta: FrameMetaV1, /
        ) -> Any: ...


SupportsFrameReady: TypeAlias = "FrameReady0 | FrameReady1 | FrameReady2 | FrameReady3"
SingleOutput: TypeAlias = "Path | str | SupportsFrameReady | BaseRunnerHandler"

MSG = (
    "This sequence is a placeholder for a generator of events with unknown "
    "length & shape. Iterating over it has no effect."
)

_STOP = object()


class _PrepareMsg(NamedTuple):
    sequence: MDASequence
    meta: SummaryMetaV1 | None


class _WriteFrameMsg(NamedTuple):
    img: np.ndarray
    event: MDAEvent
    meta: FrameMetaV1


class _CleanupMsg(NamedTuple):
    sequence: MDASequence


_HandlerMsg = _PrepareMsg | _WriteFrameMsg | _CleanupMsg


def _frameReady_nparams(handler: Any) -> int:
    """Return the number of positional parameters for handler.frameReady."""
    sig = inspect.signature(handler.frameReady)
    return sum(
        1
        for p in sig.parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        and p.default is p.empty
    )


class _HandlersThread:
    """Background thread that dispatches handler calls from a queue.

    Handles both `BaseRunnerHandler` (prepare/writeframe/cleanup) and
    `SupportsFrameReady` (sequenceStarted/frameReady/sequenceFinished) handlers
    in a single unified queue.
    """

    def __init__(self) -> None:
        self._handlers: list[BaseRunnerHandler | SupportsFrameReady] = []
        self._runner_handlers: list[BaseRunnerHandler] = []
        self._signal_handlers: list[tuple[Any, int]] = []  # (handler, nparams)
        self._queue: queue.Queue[_HandlerMsg | object] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None

    def __iter__(self) -> Iterator[BaseRunnerHandler | SupportsFrameReady]:
        return iter(self._handlers)

    def set_handlers(
        self,
        handlers: list[BaseRunnerHandler | SupportsFrameReady],
    ) -> None:
        """Set the handler list, caching frameReady parameter counts."""
        self.clear()

        self._handlers = list(handlers)

        for h in self._handlers:
            if isinstance(h, BaseRunnerHandler):
                self._runner_handlers.append(h)
            else:
                nparams = _frameReady_nparams(h)
                self._signal_handlers.append((h, nparams))

    def clear(self) -> None:
        """Clear all handlers."""
        self._handlers.clear()
        self._runner_handlers.clear()
        self._signal_handlers.clear()

    def start(self) -> None:
        """Start the background dispatch thread (no-op if no handlers)."""
        self._error = None
        if not self._handlers:
            return
        # drain any stale messages from a previous (possibly failed) run
        while not self._queue.empty():
            self._queue.get_nowait()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def enqueue_prepare(
        self, sequence: MDASequence, meta: SummaryMetaV1 | None
    ) -> None:
        """Enqueue a prepare message for all handlers."""
        if self._thread is None:
            return
        self._check_error()
        self._queue.put(_PrepareMsg(sequence, meta))

    def enqueue_frame(
        self, img: np.ndarray, event: MDAEvent, meta: FrameMetaV1
    ) -> None:
        """Enqueue a frame message for all handlers."""
        if self._thread is None:
            return
        self._check_error()
        self._queue.put(_WriteFrameMsg(img, event, meta))

    def enqueue_cleanup(self, sequence: MDASequence) -> None:
        """Enqueue a cleanup message for all handlers."""
        if self._thread is None:
            return
        self._check_error()
        self._queue.put(_CleanupMsg(sequence))

    def stop_and_join(self) -> None:
        """Send stop sentinel and wait for the thread to finish."""
        if self._thread is not None:
            self._queue.put(_STOP)
            self._thread.join()
            self._thread = None
        # ensure handlers are cleared even if _dispatch_cleanup didn't run
        # (e.g. thread died from a handler error before processing cleanup)
        self.clear()
        self._check_error()

    def _run(self) -> None:
        """Background thread: drain the queue and dispatch to handlers."""
        while True:
            item = self._queue.get()
            if item is _STOP:
                break
            try:
                if isinstance(item, _PrepareMsg):
                    self._dispatch_prepare(item.sequence, item.meta)
                elif isinstance(item, _WriteFrameMsg):
                    self._dispatch_frame(item.img, item.event, item.meta)
                elif isinstance(item, _CleanupMsg):
                    self._dispatch_cleanup(item.sequence)
            except Exception as e:
                self._error = e
                break

    def _dispatch_prepare(
        self, sequence: MDASequence, meta: SummaryMetaV1 | None
    ) -> None:
        """Call prepare on runner handlers and sequenceStarted on signal handlers."""
        for h in self._runner_handlers:
            h.prepare(sequence, meta)
        for h, _ in self._signal_handlers:
            if hasattr(h, "sequenceStarted"):
                try:
                    h.sequenceStarted(sequence, meta)
                except TypeError:
                    h.sequenceStarted(sequence)

    def _dispatch_frame(
        self, img: np.ndarray, event: MDAEvent, meta: FrameMetaV1
    ) -> None:
        """Call writeframe on runner handlers and frameReady on signal handlers."""
        for h in self._runner_handlers:
            h.writeframe(img, event, meta)
        args = (img, event, meta)
        for h, nparams in self._signal_handlers:
            h.frameReady(*args[:nparams])

    def _dispatch_cleanup(self, sequence: MDASequence) -> None:
        """Call cleanup on runner handlers and sequenceFinished on signal handlers."""
        for h in self._runner_handlers:
            h.cleanup()
        for h, _ in self._signal_handlers:
            if hasattr(h, "sequenceFinished"):
                h.sequenceFinished(sequence)

        # clear handler lists so get_output_handlers() returns empty
        # before sequenceFinished is emitted on the main thread
        self.clear()

    def _check_error(self) -> None:
        if self._error is not None:
            raise RuntimeError("Handler dispatch thread failed") from self._error


class GeneratorMDASequence(MDASequence):
    axis_order: tuple[str, ...] = ()

    @property
    def sizes(self) -> dict[str, int]:  # pragma: no cover
        warnings.warn(MSG, stacklevel=2)
        return {}

    def iter_axis(self, axis: str) -> Iterator:  # pragma: no cover
        warnings.warn(MSG, stacklevel=2)
        yield from []

    def __str__(self) -> str:
        return "GeneratorMDASequence()"


class MDARunner:
    """Object that executes a multi-dimensional experiment using an MDAEngine.

    This object is available at [`CMMCorePlus.mda`][pymmcore_plus.CMMCorePlus.mda].

    This is the main object that runs a multi-dimensional experiment; it does so by
    driving an acquisition engine that implements the
    [`PMDAEngine`][pymmcore_plus.mda.PMDAEngine] protocol.  It emits signals at specific
    times during the experiment (see
    [`PMDASignaler`][pymmcore_plus.mda.events.PMDASignaler] for details on the signals
    that are available to connect to and when they are emitted).
    """

    def __init__(self) -> None:
        self._engine: PMDAEngine | None = None
        self._signals = _get_auto_MDA_callback_class()()
        self._running = False
        self._paused = False
        self._paused_time: float = 0
        self._pause_interval: float = 0.1  # sec to wait between checking pause state
        self._handlers_thread = _HandlersThread()
        self._canceled = False
        self._sequence: MDASequence | None = None
        # timer for the full sequence, reset only once at the beginning of the sequence
        self._sequence_t0: float = 0.0
        # event clock, reset whenever `event.reset_event_timer` is True
        self._t0: float = 0.0

    def set_engine(self, engine: PMDAEngine) -> PMDAEngine | None:
        """Set the [`PMDAEngine`][pymmcore_plus.mda.PMDAEngine] to use for the MDA run."""  # noqa: E501
        # MagicMock on py312 no longer satisfies isinstance ... so we explicitly
        # allow it here just for the sake of testing.
        if not isinstance(engine, (PMDAEngine, MagicMock)):
            raise TypeError("Engine does not conform to the Engine protocol.")

        if self.is_running():  # pragma: no cover
            raise RuntimeError(
                "Cannot register a new engine when the current engine is running "
                "an acquisition. Please cancel the current engine's acquisition "
                "before registering"
            )

        old_engine, self._engine = self._engine, engine
        return old_engine

    # NOTE:
    # this return annotation is a lie, since the user can set it to their own engine.
    # but in MOST cases, this is the engine that will be used by default, so it's
    # convenient for IDEs to point to this rather than the abstract protocol.
    @property
    def engine(self) -> MDAEngine | None:
        """The [`PMDAEngine`][pymmcore_plus.mda.PMDAEngine] that is currently being used."""  # noqa: E501
        return self._engine  # type: ignore

    @property
    def events(self) -> PMDASignaler:
        """Signals that are emitted during the MDA run.

        See [`PMDASignaler`][pymmcore_plus.mda.PMDASignaler] for details on the
        signals that are available to connect to.
        """
        return self._signals

    def is_running(self) -> bool:
        """Return True if an acquisition is currently underway.

        This will return True at any point between the emission of the
        [`sequenceStarted`][pymmcore_plus.mda.PMDASignaler.sequenceStarted] and
        [`sequenceFinished`][pymmcore_plus.mda.PMDASignaler.sequenceFinished] signals,
        including when the acquisition is currently paused.

        Returns
        -------
        bool
            Whether an acquisition is underway.
        """
        return self._running

    def is_paused(self) -> bool:
        """Return True if the acquisition is currently paused.

        Use `toggle_pause` to change the paused state.

        Returns
        -------
        bool
            Whether the current acquisition is paused.
        """
        return self._paused

    def cancel(self) -> None:
        """Cancel the currently running acquisition.

        This is a no-op if no acquisition is currently running.
        If an acquisition is running then this will cancel the acquisition and
        a sequenceCanceled signal, followed by a sequenceFinished signal will
        be emitted.
        """
        self._canceled = True
        self._paused_time = 0

    def toggle_pause(self) -> None:
        """Toggle the paused state of the current acquisition.

        To get whether the acquisition is currently paused use the
        [`is_paused`][pymmcore_plus.mda.MDARunner.is_paused] method. This method is a
        no-op if no acquisition is currently underway.
        """
        if self.is_running():
            self._paused = not self._paused
            self._signals.sequencePauseToggled.emit(self._paused)

    def run(
        self,
        events: Iterable[MDAEvent],
        *,
        output: SingleOutput | Sequence[SingleOutput] | None = None,
    ) -> None:
        """Run the multi-dimensional acquisition defined by `sequence`.

        Most users should not use this directly as it will block further
        execution. Instead, use the
        [`CMMCorePlus.run_mda`][pymmcore_plus.CMMCorePlus.run_mda] method which will
        run on a thread.

        Parameters
        ----------
        events : Iterable[MDAEvent]
            An iterable of `useq.MDAEvents` objects to execute.
        output : SingleOutput | Sequence[SingleOutput] | None, optional
            The output handler(s) to use.  If None, no output will be saved.
            The value may be either a single output or a sequence of outputs,
            where a "single output" can be any of the following:

            - A string or Path to a file path. A handler will be created
                automatically based on the extension of the path.
                - `.zarr` or `.ome.zarr` paths will use `OMERunnerHandler`
                - `.ome.tiff` or `.tif` paths will use `OMERunnerHandler`
                - A directory with no extension will use `ImageSequenceWriter`
            - A `BaseRunnerHandler` instance (e.g. `OMERunnerHandler`) for
                runner-managed writing via `prepare`/`writeframe`/`cleanup`.
            - A handler object with a `frameReady` method for signal-based
                writing.  See `mda_listeners_connected` for more details.

            During the course of the sequence, the `get_output_handlers` method can be
            used to get the currently connected output handlers (including those that
            were created automatically based on file paths).
        """
        error = None
        sequence = events if isinstance(events, MDASequence) else GeneratorMDASequence()

        with self._set_handlers(output):
            try:
                engine = self._prepare_to_run(sequence)
                self._run(engine, events)
            except Exception as e:
                error = e
            with exceptions_logged():
                self._finish_run(sequence)
        if error is not None:
            raise error

    def get_output_handlers(self) -> tuple[SupportsFrameReady | BaseRunnerHandler, ...]:
        """Return the data handlers that are currently connected.

        Output handlers are connected by passing them to the `output` parameter of the
        `run` method; the run method accepts objects with a `frameReady` method *or*
        strings representing paths.  If a string is passed, a handler will be created
        internally.

        This method returns a tuple of all currently connected handlers, including both
        signal-based handlers (with a `frameReady` method) and runner handlers (with
        `prepare`/`writeframe`/`cleanup` methods).

        Handlers are cleared each time `run()` is called, (but not at the end
        of the sequence).

        Returns
        -------
        tuple[SupportsFrameReady | BaseRunnerHandler, ...]
            Tuple of all connected output handlers.
        """
        return tuple(self._handlers_thread)

    def seconds_elapsed(self) -> float:
        """Return the number of seconds since the start of the acquisition."""
        return time.perf_counter() - self._sequence_t0

    def event_seconds_elapsed(self) -> float:
        """Return the number of seconds on the "event clock".

        This is the time since either the start of the acquisition or the last
        event with `reset_event_timer` set to `True`.
        """
        return time.perf_counter() - self._t0

    @contextmanager
    def _set_handlers(
        self, output: SingleOutput | Sequence[SingleOutput] | None
    ) -> Iterator[None]:
        """Context in which output handlers are initialized in the background thread."""
        if output is None:
            yield
            return

        if isinstance(output, (str, Path)) or not isinstance(output, Sequence):
            output = [output]

        handlers: list[BaseRunnerHandler | SupportsFrameReady] = []
        for item in output:
            if isinstance(item, (str, Path)):
                item = self._handler_for_path(item)
            if not isinstance(item, BaseRunnerHandler):
                if not callable(getattr(item, "frameReady", None)):
                    raise TypeError(
                        "Output handlers must have a callable frameReady method. "
                        f"Got {item} with type {type(item)}."
                    )
            handlers.append(item)

        # add the handlers to the thread
        self._handlers_thread.set_handlers(handlers)
        yield

    @staticmethod
    def _handler_for_path(
        path: str | Path,
    ) -> BaseRunnerHandler | ImageSequenceWriter:
        """Convert a string or Path into a handler object.

        This method picks from the built-in handlers based on the extension of the path.
        """
        from pymmcore_plus.mda.handlers import handler_for_path

        return handler_for_path(path)

    def _run(self, engine: PMDAEngine, events: Iterable[MDAEvent]) -> None:
        """Main execution of events, inside the try/except block of `run`."""
        teardown_event = getattr(engine, "teardown_event", lambda e: None)
        if isinstance(events, Iterator):
            # if an iterator is passed directly, then we use that iterator
            # instead of the engine's event_iterator.  Directly passing an iterator
            # is an advanced use case, (for example, `iter(Queue(), None)` for event-
            # driven acquisition) and we don't want the engine to interfere with it.
            event_iterator = iter
        else:
            event_iterator = getattr(engine, "event_iterator", iter)
        _events: Iterator[MDAEvent] = event_iterator(events)
        self._reset_event_timer()
        self._sequence_t0 = self._t0

        for event in _events:
            if event.reset_event_timer:
                self._reset_event_timer()
            # If cancelled break out of the loop
            if self._wait_until_event(event) or not self._running:
                break

            self._signals.eventStarted.emit(event)
            logger.info("%s", event)
            engine.setup_event(event)

            try:
                runner_time_ms = self.seconds_elapsed() * 1000
                # this is a bit of a hack to pass the time into the engine
                # it is used for intra-event time calculations inside the engine.
                # we pop it off after the event is executed.
                event.metadata["runner_t0"] = self._sequence_t0
                output = engine.exec_event(event) or ()  # in case output is None
                for payload in output:
                    img, event, meta = payload
                    event.metadata.pop("runner_t0", None)
                    # if the engine calculated its own time, don't overwrite it
                    if "runner_time_ms" not in meta:
                        meta["runner_time_ms"] = runner_time_ms

                    # enqueue frame in the handler thread
                    self._handlers_thread.enqueue_frame(img, event, meta)

                    with exceptions_logged():
                        self._signals.frameReady.emit(img, event, meta)
            finally:
                teardown_event(event)

    def _prepare_to_run(self, sequence: MDASequence) -> PMDAEngine:
        """Set up for the MDA run.

        Parameters
        ----------
        sequence : MDASequence
            The sequence of events to run.
        """
        if not self._engine:  # pragma: no cover
            raise RuntimeError("No MDAEngine set.")

        self._running = True
        self._paused = False
        self._paused_time = 0.0
        self._sequence = sequence

        meta = self._engine.setup_sequence(sequence)

        # start the handler thread and enqueue the prepare calls
        self._handlers_thread.start()
        self._handlers_thread.enqueue_prepare(sequence, meta)

        self._signals.sequenceStarted.emit(sequence, meta or {})
        logger.info("MDA Started: %s", sequence)
        return self._engine

    def _reset_event_timer(self) -> None:
        self._t0 = time.perf_counter()  # reference time, in seconds

    def _check_canceled(self) -> bool:
        """Return True if the cancel method has been called and emit relevant signals.

        If cancelled, this relies on the `self._sequence` being the current sequence
        in order to emit a `sequenceCanceled` signal.

        Returns
        -------
        bool
            Whether the MDA has been canceled.
        """
        if self._canceled:
            logger.warning("MDA Canceled: %s", self._sequence)
            self._signals.sequenceCanceled.emit(self._sequence)
            self._canceled = False
            return True
        return False

    def _wait_until_event(self, event: MDAEvent) -> bool:
        """Wait until the event's min start time, checking for pauses cancellations.

        Parameters
        ----------
        event : MDAEvent
            The event to wait for.

        Returns
        -------
        bool
            Whether the MDA was cancelled while waiting.
        """
        if not self.is_running():
            return False  # pragma: no cover
        if self._check_canceled():
            return True
        while self.is_paused() and not self._canceled:
            self._paused_time += self._pause_interval  # fixme: be more precise
            time.sleep(self._pause_interval)

            if self._check_canceled():
                return True

        # FIXME: this is actually the only place where the runner assumes our event is
        # an MDAevent.  For everything else, the engine is technically the only thing
        # that cares about the event time.
        # So this whole method could potentially be moved to the engine.
        if event.min_start_time:
            go_at = event.min_start_time + self._paused_time
            # We need to enter a loop here checking paused and canceled.
            # otherwise you'll potentially wait a long time to cancel
            remaining_wait_time = go_at - self.event_seconds_elapsed()
            while remaining_wait_time > 0:
                self._signals.awaitingEvent.emit(event, remaining_wait_time)
                while self._paused and not self._canceled:
                    self._paused_time += self._pause_interval  # fixme: be more precise
                    remaining_wait_time += self._pause_interval
                    time.sleep(self._pause_interval)

                if self._canceled:
                    break
                time.sleep(min(remaining_wait_time, 0.5))
                remaining_wait_time = go_at - self.event_seconds_elapsed()

        # check canceled again in case it was canceled
        # during the waiting loop
        return self._check_canceled()

    def _finish_run(self, sequence: MDASequence) -> None:
        """To be called at the end of an acquisition.

        Parameters
        ----------
        sequence : MDASequence
            The sequence that was finished.
        """
        self._running = False
        self._canceled = False

        if hasattr(self._engine, "teardown_sequence"):
            self._engine.teardown_sequence(sequence)  # type: ignore

        logger.info("MDA Finished: %s", sequence)

        # enqueue cleanup and wait for the handler thread to finish
        self._handlers_thread.enqueue_cleanup(sequence)
        self._handlers_thread.stop_and_join()

        self._signals.sequenceFinished.emit(sequence)
