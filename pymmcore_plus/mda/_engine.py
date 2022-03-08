import time
from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from loguru import logger
from useq import MDAEvent, MDASequence

from .events import PMDASignaler, _get_auto_MDA_callback_class

if TYPE_CHECKING:
    from ..core import CMMCorePlus


@runtime_checkable
class PMDAEngine(Protocol):
    @property
    @abstractmethod
    def events(self) -> PMDASignaler:
        """Return the MDA events object."""

    @abstractmethod
    def is_running(self) -> bool:
        """Return whether currently running an Acquistion"""

    @abstractmethod
    def cancel(self):
        """Cancel the MDA."""

    @abstractmethod
    def toggle_pause(self):
        """Switch whether the MDA is paused."""

    @abstractmethod
    def is_paused(self) -> bool:
        """Returns whether the acquistion is currently paused."""

    @abstractmethod
    def run(self, sequence: MDASequence):
        """Start the acquisition loop blocking the current thread."""


class MDAEngine(PMDAEngine):
    def __init__(self, mmc: "CMMCorePlus" = None) -> None:
        self._mmc = mmc
        self._events = _get_auto_MDA_callback_class()()
        self._canceled = False
        self._paused = False
        self._running = False

    @property
    def events(self) -> PMDASignaler:
        return self._events

    def is_running(self) -> bool:
        """
        Return whether an acquistion is currently underway.

        This will return True at any point between the emission of the
        ``sequenceStarted`` and ``sequenceFinished`` signals, including when
        the acquisition is currently paused.

        Returns
        -------
        bool
            Whether an acquistion is underway.
        """
        return self._running

    def cancel(self):
        """
        Cancel the currently running acquisition.

        This is a no-op if no acquisition is currently running.
        If an acquisition is running then this will cancel the acquistion and
        a sequenceCanceled signal, followed by a sequenceFinished signal will
        be emitted.
        """
        self._canceled = True
        self._paused_time = 0
        self._t0 = None

    def toggle_pause(self):
        """
        Toggle the paused state of the current acquisition.

        To get whether the acquisition is currently paused use the
        ``is_paused`` method. This method is a no-op if no acquistion is
        currently underway.
        """
        if self._running:
            self._paused = not self._paused
            self._events.sequencePauseToggled.emit(self._paused)

    def is_paused(self) -> bool:
        """
        Return whether the acquistion is currently paused.

        Use ``toggle_pause`` to change the paused state.

        Returns
        -------
        bool
            Whether the current acquistion is paused.
        """
        return self._paused

    def _prepare_to_run(self, sequence: MDASequence):
        """
        Set up for the MDA run - defining private variables and emitting sequenceStarted

        Parameters
        ----------
        sequence : MDASequence
        """
        self._running = True
        # instancing here rather than in init to avoid
        # recursion in the CMMCorePlus init
        from ..core import CMMCorePlus

        self._mmc = self._mmc or CMMCorePlus.instance()
        self._events.sequenceStarted.emit(sequence)
        self._sequence = sequence
        logger.info("MDA Started: {}", sequence)
        self._paused = False
        self._paused_time = 0.0
        self._t0 = time.perf_counter()  # reference time, in seconds

    def _check_canceled(self) -> bool:
        """
        Check if the cancel() method has been called and emit relevant signals.

        If cancelled this relies on the self._sequence being the current sequence
        in order to emit a sequenceCanceled signal.

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

    def _wait_until_event(self, event: MDAEvent, sequence: MDASequence) -> bool:
        """
        Wait until the event's min start time, checking for pauses
        cancelations.

        Parameters
        ----------
        event : MDAEvent
        sequence : MDASequence

        Returns
        -------
        bool
            Whether the MDA was cancelled while waiting.
        """
        if not self._running:
            return
        if self._check_canceled():
            return True
        while self._paused and not self._canceled:
            self._paused_time += 0.1  # fixme: be more precise
            time.sleep(0.1)

            if self._check_canceled():
                return True

            if event.min_start_time:
                go_at = event.min_start_time + self._paused_time
                # We need to enter a loop here checking paused and canceled.
                # otherwise you'll potentially wait a long time to cancel
                to_go = go_at - (time.perf_counter() - self._t0)
                while to_go > 0:
                    while self._paused and not self._canceled:
                        self._paused_time += 0.1  # fixme: be more precise
                        to_go += 0.1
                        time.sleep(0.1)

                    if self._canceled:
                        break
                    if to_go > 0.5:
                        time.sleep(0.5)
                    else:
                        time.sleep(to_go)
                    to_go = go_at - (time.perf_counter() - self._t0)

        # check canceled again in case it was canceled
        # during the waiting loop
        if self._check_canceled():
            return True
        return False

    def _prep_hardware(self, event: MDAEvent, waitForSystem: bool = True):
        """
        Set the system hardware (XY, Z, channel, exposure) as defined in the event.

        Parameters
        ----------
        event : MDAEvent
            The event to use for the Hardware config
        waitForSystem : bool
            Whether to call `core.waitForSystem()`
        """
        if not self._running:
            return
        if event.x_pos is not None or event.y_pos is not None:
            x = event.x_pos or self._mmc.getXPosition()
            y = event.y_pos or self._mmc.getYPosition()
            self._mmc.setXYPosition(x, y)
        if event.z_pos is not None:
            self._mmc.setZPosition(event.z_pos)
        if event.channel is not None:
            self._mmc.setConfig(event.channel.group, event.channel.config)
        if event.exposure is not None:
            self._mmc.setExposure(event.exposure)

        if waitForSystem:
            self._mmc.waitForSystem()

    def _finish_run(self, sequence: MDASequence):
        """
        To be called at the end of an acquisition.

        Parameters
        ----------
        sequence : MDASequence
            The sequence that was finished.
        """
        logger.info("MDA Finished: {}", sequence)
        self._running = False
        self._events.sequenceFinished.emit(sequence)

    def run(self, sequence: MDASequence) -> None:
        """
        Run the multi-dimensional acquistion defined by `sequence`.

        Most users should not use this directly as it will block further
        execution. Instead use ``run_mda`` on CMMCorePlus which will run on
        a thread.

        Parameters
        ----------
        sequence : MDASequence
            The sequence of events to run.
        """
        self._prepare_to_run(sequence)

        for event in sequence:
            cancelled = self._wait_until_event(event, sequence)

            # If cancelled break out of the loop
            if cancelled:
                break

            logger.info(event)
            self._prep_hardware(event)

            self._mmc.snapImage()
            img = self._mmc.getImage()

            self._events.frameReady.emit(img, event)
        self._finish_run(sequence)
