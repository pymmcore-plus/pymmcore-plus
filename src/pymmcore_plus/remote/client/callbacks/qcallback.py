from Pyro5.api import expose
from qtpy.QtCore import QObject, Signal

# For some reason, subclassing from core.events._qsignals seems to sometimes affect
# the event emission order in the tests.  Not sure why, so keeping this as it's own
# class for now


class QCoreSignaler(QObject):
    """Qt-backed CMMCoreSignaler."""

    # native MMCore callback events
    propertiesChanged = Signal()
    propertyChanged = Signal(str, str, object)
    channelGroupChanged = Signal(str)
    configGroupChanged = Signal(str, str)
    configSet = Signal(str, str)
    systemConfigurationLoaded = Signal()
    pixelSizeChanged = Signal(float)
    pixelSizeAffineChanged = Signal(float, float, float, float, float, float)
    stagePositionChanged = Signal(str, float)
    XYStagePositionChanged = Signal(str, float, float)
    xYStagePositionChanged = XYStagePositionChanged  # alias
    exposureChanged = Signal(str, float)
    SLMExposureChanged = Signal(str, float)
    sLMExposureChanged = SLMExposureChanged  # alias

    # added for CMMCorePlus
    sequenceStarted = Signal(object)  # at the start of an MDA sequence
    sequencePauseToggled = Signal(bool)  # when MDA is paused/unpaused
    sequenceCanceled = Signal(object)  # when mda is canceled
    sequenceFinished = Signal(object)  # when mda is done (whether canceled or not)
    frameReady = Signal(object, object)  # after each event in the sequence
    imageSnapped = Signal(object)  # after an image is snapped

    @expose
    def receive_core_callback(self, signal_name, args) -> None:
        """Will be called by server with name of signal, and tuple of args."""
        # let it throw an exception.
        getattr(self, signal_name).emit(*args)
