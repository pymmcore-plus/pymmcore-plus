import time
from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from loguru import logger
from useq import MDASequence

from .events import PMDASignaler, _get_auto_MDA_callback_class

if TYPE_CHECKING:
    from ..core import CMMCorePlus


@runtime_checkable
class PMDAEngine(Protocol):
    @property
    @abstractmethod
    def events(self) -> PMDASignaler:
        """Returns the signaler object."""
        ...

    @abstractmethod
    def cancel(self):
        """Cancel the MDA."""
        ...

    @abstractmethod
    def toggle_pause(self):
        """Switch whether the MDA is paused."""
        ...

    @abstractmethod
    def is_paused(self) -> bool:
        """Returns whether the acquistion is currently paused."""
        ...

    @abstractmethod
    def run(self, sequence: MDASequence):
        """Start the acquisition loop blocking the current thread."""
        ...


class MDAEngine:
    def __init__(self, mmc: "CMMCorePlus") -> None:
        self.events = _get_auto_MDA_callback_class()()
        # we can't use the Instance approach here
        # because this will be called from the init of CMMCorePlus
        # which means that no instance exists yet and then... badness
        self._mmc = mmc
        self._canceled = False
        self._paused = False

    def cancel(self):
        self._canceled = True

    def toggle_pause(self):
        self._paused = not self._paused
        self.events.sequencePauseToggled.emit(self._paused)

    def run(self, sequence: MDASequence) -> None:
        self.events.sequenceStarted.emit(sequence)
        logger.info("MDA Started: {}", sequence)
        self._paused = False
        paused_time = 0.0
        t0 = time.perf_counter()  # reference time, in seconds

        def check_canceled():
            if self._canceled:
                logger.warning("MDA Canceled: {}", sequence)
                self.events.sequenceCanceled.emit(sequence)
                self._canceled = False
                return True
            return False

        for event in sequence:
            while self._paused and not self._canceled:
                paused_time += 0.1  # fixme: be more precise
                time.sleep(0.1)

            if check_canceled():
                break

            if event.min_start_time:
                go_at = event.min_start_time + paused_time
                # We need to enter a loop here checking paused and canceled.
                # otherwise you'll potentially wait a long time to cancel
                to_go = go_at - (time.perf_counter() - t0)
                while to_go > 0:
                    while self._paused and not self._canceled:
                        paused_time += 0.1  # fixme: be more precise
                        to_go += 0.1
                        time.sleep(0.1)

                    if self._canceled:
                        break
                    if to_go > 0.5:
                        time.sleep(0.5)
                    else:
                        time.sleep(to_go)
                    to_go = go_at - (time.perf_counter() - t0)

            # check canceled again in case it was canceled
            # during the waiting loop
            if check_canceled():
                break

            logger.info(event)

            # prep hardware
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

            # acquire
            self._mmc.waitForSystem()
            self._mmc.snapImage()
            img = self._mmc.getImage()

            self.events.frameReady.emit(img, event)

        logger.info("MDA Finished: {}", sequence)
        self.events.sequenceFinished.emit(sequence)
