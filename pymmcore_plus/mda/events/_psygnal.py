import numpy as np
from psygnal import Signal
from useq import MDAEvent, MDASequence


class MDASignaler:
    sequenceStarted = Signal(MDASequence)  # at the start of an MDA sequence
    sequencePauseToggled = Signal(bool)  # when MDA is paused/unpaused
    sequenceCanceled = Signal(MDASequence)  # when mda is canceled
    sequenceFinished = Signal(MDASequence)  # when mda is done (whether canceled or not)
    frameReady = Signal(np.ndarray, MDAEvent)  # after each event in the sequence
