from __future__ import annotations

import time
import warnings
from contextlib import nullcontext
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    ContextManager,
    Iterable,
    Iterator,
    Sequence,
    Tuple,
)
from unittest.mock import MagicMock

from useq import MDASequence

from pymmcore_plus._logger import exceptions_logged, logger

from ._protocol import PMDAEngine
from ._thread_relay import mda_listeners_connected
from .events import PMDASignaler, _get_auto_MDA_callback_class

if TYPE_CHECKING:
    from typing import TypeAlias

    from useq import MDAEvent

    from ._engine import MDAEngine

    SingleOutput: TypeAlias = Path | str | object

MSG = (
    "This sequence is a placeholder for a generator of events with unknown "
    "length & shape. Iterating over it has no effect."
)


class GeneratorMDASequence(MDASequence):
    axis_order: Tuple[str, ...] = ()  # noqa: UP006

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

        self._canceled = False
        self._sequence: MDASequence | None = None
        self._reset_timer()

    def set_engine(self, engine: PMDAEngine) -> PMDAEngine | None:
        """Set the [`PMDAEngine`][pymmcore_plus.mda.PMDAEngine] to use for the MDA run."""  # noqa: E501
        # MagicMock on py312 no longer satisfies isinstance ... so we explicitly
        # allow it here just for the sake of testing.
        if not isinstance(engine, (PMDAEngine, MagicMock)):
            raise TypeError("Engine does not conform to the Engine protocol.")

        if self.is_running():  # pragma: no cover
            raise RuntimeError(
                "Cannot register a new engine when the current engine is running "
                "an acquistion. Please cancel the current engine's acquistion "
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
        """Return True if an acquistion is currently underway.

        This will return True at any point between the emission of the
        [`sequenceStarted`][pymmcore_plus.mda.PMDASignaler.sequenceStarted] and
        [`sequenceFinished`][pymmcore_plus.mda.PMDASignaler.sequenceFinished] signals,
        including when the acquisition is currently paused.

        Returns
        -------
        bool
            Whether an acquistion is underway.
        """
        return self._running

    def is_paused(self) -> bool:
        """Return True if the acquistion is currently paused.

        Use `toggle_pause` to change the paused state.

        Returns
        -------
        bool
            Whether the current acquistion is paused.
        """
        return self._paused

    def cancel(self) -> None:
        """Cancel the currently running acquisition.

        This is a no-op if no acquisition is currently running.
        If an acquisition is running then this will cancel the acquistion and
        a sequenceCanceled signal, followed by a sequenceFinished signal will
        be emitted.
        """
        self._canceled = True
        self._paused_time = 0

    def toggle_pause(self) -> None:
        """Toggle the paused state of the current acquisition.

        To get whether the acquisition is currently paused use the
        [`is_paused`][pymmcore_plus.mda.MDARunner.is_paused] method. This method is a
        no-op if no acquistion is currently underway.
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
        """Run the multi-dimensional acquistion defined by `sequence`.

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

    def _outputs_connected(
        self, output: SingleOutput | Sequence[SingleOutput] | None
    ) -> ContextManager:
        """Context in which output handlers are connected to the frameReady signal."""
        if output is None:
            return nullcontext()

        if isinstance(output, (str, Path)) or not isinstance(output, Sequence):
            output = [output]

        # convert all items to handler objects
        handlers: list[Any] = []
        for item in output:
            if isinstance(item, (str, Path)):
                handlers.append(self._handler_for_path(item))
            else:
                # TODO: better check for valid handler protocol
                # quick hack for now.
                if not hasattr(item, "frameReady"):
                    raise TypeError(
                        "Output handlers must have a frameReady method. "
                        f"Got {item} with type {type(item)}."
                    )
                handlers.append(item)

        return mda_listeners_connected(*handlers, mda_events=self._signals)

    def _handler_for_path(self, path: str | Path) -> object:
        """Convert a string or Path into a handler object.

        This method picks from the built-in handlers based on the extension of the path.
        """
        path = str(Path(path).expanduser().resolve())
        if path.endswith(".zarr"):
            from pymmcore_plus.mda.handlers import OMEZarrWriter

            return OMEZarrWriter(path)

        if path.endswith((".tiff", ".tif")):
            from pymmcore_plus.mda.handlers import OMETiffWriter

            return OMETiffWriter(path)

        # FIXME: ugly hack for the moment to represent a non-existent directory
        # there are many features that ImageSequenceWriter supports, and it's unclear
        # how to infer them all from a single string.
        if not (Path(path).suffix or Path(path).exists()):
            from pymmcore_plus.mda.handlers import ImageSequenceWriter

            return ImageSequenceWriter(path)

        raise ValueError(f"Could not infer a writer handler for path: '{path}'")

    def _run(self, engine: PMDAEngine, events: Iterable[MDAEvent]) -> None:
        """Main execution of events, inside the try/except block of `run`."""
        teardown_event = getattr(engine, "teardown_event", lambda e: None)
        event_iterator = getattr(engine, "event_iterator", iter)
        _events: Iterator[MDAEvent] = event_iterator(events)

        for event in _events:
            # If cancelled break out of the loop
            if self._wait_until_event(event) or not self._running:
                break

            self._signals.eventStarted.emit(event)
            logger.info("%s", event)
            engine.setup_event(event)

            output = engine.exec_event(event) or ()  # in case output is None

            for payload in output:
                img, event, meta = payload
                if "PerfCounter" in meta:
                    meta["ElapsedTime-ms"] = (meta["PerfCounter"] - self._t0) * 1000
                meta["Event"] = event
                with exceptions_logged():
                    self._signals.frameReady.emit(img, event, meta)

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
        logger.info("MDA Started: %s", sequence)

        self._signals.sequenceStarted.emit(sequence, meta or {})
        self._reset_timer()
        return self._engine

    def _reset_timer(self) -> None:
        self._t0 = time.perf_counter()  # reference time, in seconds

    def _time_elapsed(self) -> float:
        return time.perf_counter() - self._t0

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
            remaining_wait_time = go_at - self._time_elapsed()
            while remaining_wait_time > 0:
                self._signals.awaitingEvent.emit(event, remaining_wait_time)
                while self._paused and not self._canceled:
                    self._paused_time += self._pause_interval  # fixme: be more precise
                    remaining_wait_time += self._pause_interval
                    time.sleep(self._pause_interval)

                if self._canceled:
                    break
                time.sleep(min(remaining_wait_time, 0.5))
                remaining_wait_time = go_at - self._time_elapsed()

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


def _assert_handler(handler: Any) -> None:
    if (
        not hasattr(handler, "start")
        or not hasattr(handler, "finish")
        or not hasattr(handler, "put")
    ):
        raise TypeError("Handler must have start, finish, and put methods.")
