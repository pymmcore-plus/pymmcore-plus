from qtpy.QtCore import QObject, Signal


class QCoreCallback(QObject):
    propertiesChanged = Signal()
    propertyChanged = Signal(str, str, object)
    channelGroupChanged = Signal(str)
    configGroupChanged = Signal(str, str)
    systemConfigurationLoaded = Signal()
    pixelSizeChanged = Signal(float)
    pixelSizeAffineChanged = Signal(float, float, float, float, float, float)
    stagePositionChanged = Signal(str, float)
    XYStagePositionChanged = Signal(str, float, float)
    exposureChanged = Signal(str, float)
    SLMExposureChanged = Signal(str, float)
    MDAFrameReady = Signal(object, object)
    MDAStarted = Signal(object)
    MDACanceled = Signal()
    MDAPauseToggled = Signal(bool)
    MDAFinished = Signal(object)

    def receive_core_callback(self, signal_name, args):
        if signal_name.startswith("on"):
            signal_name = signal_name[2:]
        if not signal_name[1].isupper():
            signal_name = signal_name[0].lower() + signal_name[1:]
        # let it throw an exception.
        getattr(self, signal_name).emit(*args)
