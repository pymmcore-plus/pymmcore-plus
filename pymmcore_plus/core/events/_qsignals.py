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
    # when continuousSequenceAcquisition is started
    startContinuousSequenceAcquisition = Signal()
    # when SequenceAcquisition is started
    startSequenceAcquisition = Signal(str, int, float, bool)
    # when (Continuous)SequenceAcquisition is stopped
    stopSequenceAcquisition = Signal(str)
    autoShutterSet = Signal(bool)
    shutterSet = Signal(str, bool)

    # can't use _DevicePropertyEventMixin due to metaclass conflict
    def __init__(self) -> None:
        super().__init__()
        self._prop_callbacks: PropKeyDict = {}

    def devicePropertyChanged(
        self, device: str, property: Optional[str] = None
    ) -> _PropertySignal:
        """Return object to connect/disconnect to device/property-specific changes.

        Note that the callback provided to `.connect()` must take *two* parameters
        (property_name, new_value) if only `device` is provided, and *one* parameter
        (new_value) of both `device` and `property` are provided.

        Parameters
        ----------
        device : str
            A device label
        property : Optional[str], optional
            Optional property label.  If not provided, all property changes on `device`
            will trigger an event emission. by default None

        Returns
        -------
        _PropertySignal
            Object with `connect` and `disconnect` methods that attach a callback to
            the change event of a specific property or device.

        Examples
        --------
        >>> core.events.devicePropertyChanged('Camera', 'Gain').connect(callback)
        >>> core.events.devicePropertyChanged('Camera').connect(callback)
        """
        return _PropertySignal(self, device, property)
