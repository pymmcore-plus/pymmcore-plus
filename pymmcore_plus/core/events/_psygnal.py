import numpy as np
from psygnal import Signal

from ...mda import MDAEngine
from ._prop_event_mixin import _DevicePropertyEventMixin


class CMMCoreSignaler(_DevicePropertyEventMixin):
    """Signals that will be emitted from CMMCorePlus and RemoteMMCore objects."""

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
    imageSnapped = Signal(np.ndarray)  # whenever snap is called
    mdaEngineRegistered = Signal(MDAEngine, MDAEngine)
    startContinuousSequenceAcquisition = Signal()
    startSequenceAcquisition = Signal(str, int, float, bool)
    stopSequenceAcquisition = Signal(str)
    autoShutterSet = Signal(bool)
    shutterSet = Signal(str, bool)

    # aliases for lower casing
    @property
    def xYStagePositionChanged(self):
        return self.XYStagePositionChanged

    @property
    def sLMExposureChanged(self):
        return self.SLMExposureChanged
