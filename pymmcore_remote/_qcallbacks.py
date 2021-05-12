from qtpy.QtCore import QObject, Signal


class QCoreListener(QObject):
    onPropertiesChanged = Signal()
    onPropertyChanged = Signal(str, str, object)
    onChannelGroupChanged = Signal(str)
    onConfigGroupChanged = Signal(str, str)
    onSystemConfigurationLoaded = Signal()
    onPixelSizeChanged = Signal(float)
    onPixelSizeAffineChanged = Signal(float, float, float, float, float, float)
    onStagePositionChanged = Signal(str, float)
    onXYStagePositionChanged = Signal(str, float, float)
    onExposureChanged = Signal(str, float)
    onSLMExposureChanged = Signal(str, float)
    onMDAFrameReady = Signal(object, object)
    onMDAStarted = Signal()
    onMDACanceled = Signal()
    onMDAPaused = Signal(bool)
    onMDAFinished = Signal()

    def receive_core_callback(self, signal_name, args):
        emitter = getattr(self, signal_name, None)
        if emitter is not None:
            emitter.emit(*args)
