from psygnal import Signal, SignalGroup, SignalInstance

from pymmcore_plus.mda import MDAEngine

from ._prop_event_mixin import _DevicePropertyEventMixin


class CMMCoreSignaler(SignalGroup, _DevicePropertyEventMixin):
    """Signals that will be emitted from CMMCorePlus objects."""

    # native MMCore callback events
    propertiesChanged = Signal()
    propertyChanged = Signal(str, str, str)
    channelGroupChanged = Signal(str)
    configGroupChanged = Signal(str, str)
    configSet = Signal(str, str)
    systemConfigurationLoaded = Signal()
    pixelSizeChanged = Signal(float)
    pixelSizeAffineChanged = Signal(float, float, float, float, float, float)
    stagePositionChanged = Signal(str, float)
    XYStagePositionChanged = Signal(str, float, float)
    exposureChanged = Signal(str, float)
    SLMExposureChanged = Signal(str, float)

    # added for CMMCorePlus
    imageSnapped = Signal()  # whenever snapImage is called
    mdaEngineRegistered = Signal(MDAEngine, MDAEngine)
    continuousSequenceAcquisitionStarting = Signal()
    continuousSequenceAcquisitionStarted = Signal()
    sequenceAcquisitionStarting = Signal(str, int, float, bool)
    sequenceAcquisitionStarted = Signal(str, int, float, bool)
    sequenceAcquisitionStopped = Signal(str)
    autoShutterSet = Signal(bool)
    configGroupDeleted = Signal(str)
    configDeleted = Signal(str, str)
    configDefined = Signal(str, str, str, str, str)
    roiSet = Signal(str, int, int, int, int)

    # aliases for lower casing
    @property
    def xYStagePositionChanged(self) -> SignalInstance:  # type: ignore
        return self.XYStagePositionChanged

    @property
    def sLMExposureChanged(self) -> SignalInstance:  # type: ignore
        return self.SLMExposureChanged
