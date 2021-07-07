import numpy as np
from psygnal import Signal
from useq import MDAEvent, MDASequence


class _CMMCoreSignaler:
    # native callback events
    propertiesChanged = Signal()
    propertyChanged = Signal(str, str, str)
    channelGroupChanged = Signal(str)
    configGroupChanged = Signal(str, str)
    systemConfigurationLoaded = Signal()
    pixelSizeChanged = Signal(float)
    pixelSizeAffineChanged = Signal(float, float, float, float, float, float)
    stagePositionChanged = Signal(str, float)
    XYStagePositionChanged = Signal(str, float, float)
    exposureChanged = Signal(str, float)
    SLMExposureChanged = Signal(str, float)

    # added by CMMCorePlus
    sequenceStarted = Signal(MDASequence)
    sequencePauseToggled = Signal(MDASequence, bool)
    sequenceCanceled = Signal(MDASequence)
    sequenceFinished = Signal(MDASequence)
    frameReady = Signal(np.ndarray, MDAEvent)

    # aliases for first lowercase letter
    xYStagePositionChanged = XYStagePositionChanged
    sLMExposureChanged = SLMExposureChanged
