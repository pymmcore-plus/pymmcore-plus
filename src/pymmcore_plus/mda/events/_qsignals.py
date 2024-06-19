from qtpy.QtCore import QObject, Signal


class QMDASignaler(QObject):
    sequenceStarted = Signal(object, object)  # at the start of an MDA sequence
    sequencePauseToggled = Signal(bool)  # when MDA is paused/unpaused
    sequenceCanceled = Signal(object)  # when mda is canceled
    sequenceFinished = Signal(object)  # when mda is done (whether canceled or not)
    frameReady = Signal(object, object, object)  # img, MDAEvent, metadata
    awaitingEvent = Signal(object, float)  # MDAEvent, remaining_sec
    eventStarted = Signal(object)  # MDAEvent
