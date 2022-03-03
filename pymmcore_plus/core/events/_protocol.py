from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class SignalInstance(Protocol):
    def connect(self, slot: Callable, **kwargs: Any):
        ...

    def disconnect(self, slot: Callable, **kwargs: Any):
        ...

    def emit(self, args: Any):
        ...


@runtime_checkable
class CoreSignaler(Protocol):

    # native MMCore callback events
    propertiesChanged: SignalInstance
    propertyChanged: SignalInstance
    channelGroupChanged: SignalInstance
    configGroupChanged: SignalInstance
    configSet: SignalInstance
    systemConfigurationLoaded: SignalInstance
    pixelSizeChanged: SignalInstance
    pixelSizeAffineChanged: SignalInstance
    stagePositionChanged: SignalInstance
    XYStagePositionChanged: SignalInstance
    xYStagePositionChanged: SignalInstance  # alias
    exposureChanged: SignalInstance
    SLMExposureChanged: SignalInstance
    sLMExposureChanged: SignalInstance  # alias

    # added for CMMCorePlus
    sequenceStarted: SignalInstance
    sequencePauseToggled: SignalInstance
    sequenceCanceled: SignalInstance
    sequenceFinished: SignalInstance
    frameReady: SignalInstance
    imageSnapped: SignalInstance
