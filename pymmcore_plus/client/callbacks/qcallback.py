from Pyro5.api import expose
from qtpy.QtCore import QObject, Signal


class QCoreCallback(QObject):

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

    @expose
    def receive_core_callback(self, signal_name, args):
        # let it throw an exception.
        getattr(self, signal_name).emit(*args)
