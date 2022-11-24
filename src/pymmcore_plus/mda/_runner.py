from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, cast

from loguru import logger
from psygnal import EmitLoopError

from ._protocol import PMDAEngine
from .events import PMDASignaler, _get_auto_MDA_callback_class

if TYPE_CHECKING:
    from useq import MDAEvent, MDASequence


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
        self._events = _get_auto_MDA_callback_class()()
        self._running = False
        self._paused = False
        self._paused_time: float = 0
        self._pause_interval: float = 0.1  # sec to wait between checking pause state

        self._canceled = False
        self._sequence: MDASequence | None = None
        self._reset_timer()

    def set_engine(self, engine: PMDAEngine) -> PMDAEngine | None:
        """Set the [`PMDAEngine`][pymmcore_plus.mda.PMDAEngine] to use for the MDA run."""  # noqa: E501
        if not isinstance(engine, PMDAEngine):
            raise TypeError("Engine does not conform to the Engine protocol.")

        if self.is_running():
            raise RuntimeError(
                "Cannot register a new engine when the current engine is running "
                "an acquistion. Please cancel the current engine's acquistion "
                "before registering"
            )

        old_engine, self._engine = self._engine, engine
        return old_engine

    @property
    def engine(self) -> PMDAEngine | None:
        """The [`PMDAEngine`][pymmcore_plus.mda.PMDAEngine] that is currently being used."""  # noqa: E501
        return self._engine

    @property
    def events(self) -> PMDASignaler:
        """Signals that are emitted during the MDA run.

        See [`PMDASignaler`][pymmcore_plus.mda.PMDASignaler] for details on the
        signals that are available to connect to.
        """
        return self._events

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
            self._events.sequencePauseToggled.emit(self._paused)

    def run(self, sequence: MDASequence) -> None:
        """Run the multi-dimensional acquistion defined by `sequence`.

        Most users should not use this directly as it will block further
        execution. Instead, use the
        [`CMMCorePlus.run_mda`][pymmcore_plus.CMMCorePlus.run_mda] method which will
        run on a thread.

        Parameters
        ----------
        sequence : MDASequence
            An instance of a `useq.MDASequence` object defining the sequence of events
            to run.
        """
        try:
            self._prepare_to_run(sequence)
            self._engine = cast("PMDAEngine", self._engine)
            teardown_event = getattr(self._engine, "teardown_event", lambda e: None)

            for event in sequence:
                cancelled = self._wait_until_event(event)

                # If cancelled break out of the loop
                if cancelled:
                    break

                logger.info(event)
                if not self._running:
                    break

                self._engine.setup_event(event)

                output = self._engine.exec_event(event)

                if (img := getattr(output, "image", None)) is not None:
                    with contextlib.suppress(EmitLoopError):
                        self._events.frameReady.emit(img, event)

                teardown_event(event)

        except Exception as e:
            # clean up so future MDAs can be run
            with contextlib.suppress(Exception):
                self._finish_run(sequence)
            raise e
        self._finish_run(sequence)

    def _prepare_to_run(self, sequence: MDASequence) -> None:
        """Set up for the MDA run.

        Parameters
        ----------
        sequence : MDASequence
            The sequence of events to run.
        """
        self._running = True
        self._paused = False
        self._paused_time = 0.0
        self._sequence = sequence

        if not self._engine:
            raise RuntimeError("No MDAEngine set.")

        self._engine.setup_sequence(sequence)
        logger.info("MDA Started: {}", sequence)

        self._events.sequenceStarted.emit(sequence)
        self._reset_timer()

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
            logger.warning("MDA Canceled: {}", self._sequence)
            self._events.sequenceCanceled.emit(self._sequence)
            self._canceled = False
            return True
        return False

    def _wait_until_event(self, event: MDAEvent) -> bool:
        """Wait until the event's min start time, checking for pauses cancelations.

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
            return False
        if self._check_canceled():
            return True
        while self.is_paused() and not self._canceled:
            self._paused_time += self._pause_interval  # fixme: be more precise
            time.sleep(self._pause_interval)

            if self._check_canceled():
                return True

        if event.min_start_time:
            go_at = event.min_start_time + self._paused_time
            # We need to enter a loop here checking paused and canceled.
            # otherwise you'll potentially wait a long time to cancel
            to_go = go_at - self._time_elapsed()
            while to_go > 0:
                while self._paused and not self._canceled:
                    self._paused_time += self._pause_interval  # fixme: be more precise
                    to_go += self._pause_interval
                    time.sleep(self._pause_interval)

                if self._canceled:
                    break
                time.sleep(min(to_go, 0.5))
                to_go = go_at - self._time_elapsed()

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

        logger.info("MDA Finished: {}", sequence)
        self._events.sequenceFinished.emit(sequence)
