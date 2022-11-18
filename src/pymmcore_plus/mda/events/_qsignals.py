from qtpy.QtCore import QObject, Signal


class QMDASignaler(QObject):
    sequenceStarted = Signal(object)  # at the start of an MDA sequence
    sequencePauseToggled = Signal(bool)  # when MDA is paused/unpaused
    sequenceCanceled = Signal(object)  # when mda is canceled
    sequenceFinished = Signal(object)  # when mda is done (whether canceled or not)
    frameReady = Signal(object, object)  # after each event in the sequence
