import numpy as np
from psygnal import Signal, SignalGroup
from useq import MDAEvent, MDASequence

from pymmcore_plus.mda.events._protocol import RunStatus


class MDASignaler(SignalGroup):
    sequenceStarted = Signal(MDASequence, dict)  # at the start of an MDA sequence
    sequencePauseToggled = Signal(bool)  # when MDA is paused/unpaused
    sequenceCanceled = Signal(MDASequence)  # when mda is canceled
    sequenceFinished = Signal(
        MDASequence, RunStatus, dict, tuple
    )  # when mda is done (whether canceled or not)
    frameReady = Signal(np.ndarray, MDAEvent, dict)  # img, MDAEvent, metadata
    awaitingEvent = Signal(MDAEvent, float)  # MDAEvent, remaining_sec
    eventStarted = Signal(MDAEvent)  # MDAEvent
