from qtpy.QtCore import QObject, Signal

from pymmcore_plus.mda.events._protocol import RunStatus


class QMDASignaler(QObject):
    sequenceStarted = Signal(object, dict)  # at the start of an MDA sequence
    sequencePauseToggled = Signal(bool)  # when MDA is paused/unpaused
    sequenceCanceled = Signal(object)  # when mda is canceled
    sequenceFinished = Signal(
        object, RunStatus, dict, tuple
    )  # when mda is done (whether canceled or not)
    frameReady = Signal(object, object, dict)  # img, MDAEvent, metadata
    awaitingEvent = Signal(object, float)  # MDAEvent, remaining_sec
    eventStarted = Signal(object)  # MDAEvent
