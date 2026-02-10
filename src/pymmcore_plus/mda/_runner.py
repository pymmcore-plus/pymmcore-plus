from __future__ import annotations

import time
import warnings
from collections.abc import Iterable, Iterator, Sequence
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock
from weakref import WeakSet

from useq import MDASequence

from pymmcore_plus._logger import exceptions_logged, logger

from ._protocol import PMDAEngine
from ._thread_relay import mda_listeners_connected
from .events import PMDASignaler, _get_auto_MDA_callback_class

if TYPE_CHECKING:
    from typing import Protocol, TypeAlias

    import numpy as np
    from useq import MDAEvent

    from pymmcore_plus.metadata.schema import FrameMetaV1

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
SingleOutput: TypeAlias = "Path | str | SupportsFrameReady"

MSG = (
    "This sequence is a placeholder for a generator of events with unknown "
    "length & shape. Iterating over it has no effect."
)


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
        self._handlers: WeakSet[SupportsFrameReady] = WeakSet()
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

            - A string or Path to a directory to save images to. A handler will be
                created automatically based on the extension of the path.
                - `.zarr` files will be handled by `OMEZarrWriter`
                - `.ome.tiff` files will be handled by `OMETiffWriter`
                - A directory with no extension will be handled by `ImageSequenceWriter`
            - A handler object that implements the `DataHandler` protocol, currently
                meaning it has a `frameReady` method.  See `mda_listeners_connected`
                for more details.

            During the course of the sequence, the `get_output_handlers` method can be
            used to get the currently connected output handlers (including those that
            were created automatically based on file paths).
        """
        error = None
        sequence = events if isinstance(events, MDASequence) else GeneratorMDASequence()
        with self._outputs_connected(output):
            # NOTE: it's important that `_prepare_to_run` and `_finish_run` are
            # called inside the context manager, since the `mda_listeners_connected`
            # context manager expects to see both of those signals.
            try:
                engine = self._prepare_to_run(sequence)
                self._run(engine, events)
            except Exception as e:
                error = e
            with exceptions_logged():
                self._finish_run(sequence)
        if error is not None:
            raise error

    def get_output_handlers(self) -> tuple[SupportsFrameReady, ...]:
        """Return the data handlers that are currently connected.

        Output handlers are connected by passing them to the `output` parameter of the
        `run` method; the run method accepts objects with a `frameReady` method *or*
        strings representing paths.  If a string is passed, a handler will be created
        internally.

        This method returns a tuple of currently connected handlers, including those
        that were explicitly passed to `run()`, as well as those that were created based
        on file paths.  Internally, handlers are held by weak references, so if you want
        the handler to persist, you must keep a reference to it.  The only guaranteed
        API that the handler will have is the `frameReady` method, but it could be any
        user-defined object that implements that method.

        Handlers are cleared each time `run()` is called, (but not at the end
        of the sequence).

        Returns
        -------
        tuple[SupportsFrameReady, ...]
            Tuple of objects that (minimally) support the `frameReady` method.
        """
        return tuple(self._handlers)

    def seconds_elapsed(self) -> float:
        """Return the number of seconds since the start of the acquisition."""
        return time.perf_counter() - self._sequence_t0

    def event_seconds_elapsed(self) -> float:
        """Return the number of seconds on the "event clock".

        This is the time since either the start of the acquisition or the last
        event with `reset_event_timer` set to `True`.
        """
        return time.perf_counter() - self._t0

    def _outputs_connected(
        self, output: SingleOutput | Sequence[SingleOutput] | None
    ) -> AbstractContextManager:
        """Context in which output handlers are connected to the frameReady signal."""
        if output is None:
            return nullcontext()

        if isinstance(output, (str, Path)) or not isinstance(output, Sequence):
            output = [output]

        # convert all items to handler objects, preserving order
        _handlers: list[SupportsFrameReady] = []
        for item in output:
            if isinstance(item, (str, Path)):
                _handlers.append(self._handler_for_path(item))
            else:
                if not callable(getattr(item, "frameReady", None)):
                    raise TypeError(
                        "Output handlers must have a callable frameReady method. "
                        f"Got {item} with type {type(item)}."
                    )
                _handlers.append(item)

        self._handlers.clear()
        self._handlers.update(_handlers)
        return mda_listeners_connected(*_handlers, mda_events=self._signals)

    def _handler_for_path(self, path: str | Path) -> SupportsFrameReady:
        """Convert a string or Path into a handler object.

        This method picks from the built-in handlers based on the extension of the path.
        """
        from pymmcore_plus.mda.handlers import handler_for_path

        return cast("SupportsFrameReady", handler_for_path(path))

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
        self._signals.sequenceFinished.emit(sequence)
