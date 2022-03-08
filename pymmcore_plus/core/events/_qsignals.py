from typing import Optional

from qtpy.QtCore import QObject, Signal

from ._prop_event_mixin import PropKeyDict, _PropertySignal


class QCoreSignaler(QObject):

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
    imageSnapped = Signal(object)  # after an image is snapped
    mdaEngineRegistered = Signal(object, object)  # new engine, old engine

    # can't use _DevicePropertyEventMixin due to metaclass conflict
    def __init__(self) -> None:
        super().__init__()
        self._prop_callbacks: PropKeyDict = {}

    def devicePropertyChanged(
        self, device_label: str, property_label: Optional[str] = None
    ):
        return _PropertySignal(self, device_label, property_label)
