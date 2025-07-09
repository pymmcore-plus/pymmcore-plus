from typing import TYPE_CHECKING, Optional

from qtpy.QtCore import QObject, Signal

from ._deprecated import DeprecatedSignalProxy
from ._prop_event_mixin import _PropertySignal

if TYPE_CHECKING:
    from ._prop_event_mixin import PropKeyDict


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

    # https://github.com/micro-manager/mmCoreAndDevices/pull/659
    imageSnapped = Signal(str)  # on snapImage()
    # when (Continuous)SequenceAcquisition is stopped
    sequenceAcquisitionStopped = Signal(str)
    if TYPE_CHECKING:  # see deprecated impl below
        sequenceAcquisitionStarted = Signal(str)

    # added for CMMCorePlus
    mdaEngineRegistered = Signal(object, object)  # new engine, old engine
    # when continuousSequenceAcquisition is started
    continuousSequenceAcquisitionStarting = Signal()
    continuousSequenceAcquisitionStarted = Signal()

    if TYPE_CHECKING:
        # when SequenceAcquisition is started
        sequenceAcquisitionStarting = Signal(str)

    autoShutterSet = Signal(bool)
    configGroupDeleted = Signal(str)
    configDeleted = Signal(str, str)
    configDefined = Signal(str, str, str, str, str)
    roiSet = Signal(str, int, int, int, int)

    # can't use _DevicePropertyEventMixin due to metaclass conflict
    def __init__(self) -> None:
        super().__init__()
        self.property_callbacks: PropKeyDict = {}

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
        >>> core.events.devicePropertyChanged("Camera", "Gain").connect(callback)
        >>> core.events.devicePropertyChanged("Camera").connect(callback)
        """
        # type ignored: can't use _DevicePropertyEventMixin due to metaclass conflict
        return _PropertySignal(self, device, property)

    if not TYPE_CHECKING:
        _sequenceAcquisitionStarting = Signal(str)
        _sequenceAcquisitionStarted = Signal(str)

        # Deprecated signal wrappers for backwards compatibility
        @property
        def sequenceAcquisitionStarting(self):
            return DeprecatedSignalProxy(
                self._sequenceAcquisitionStarting,
                current_n_args=1,
                deprecated_posargs=(-1, 0, False),
            )

        @property
        def sequenceAcquisitionStarted(self):
            return DeprecatedSignalProxy(
                self._sequenceAcquisitionStarted,
                current_n_args=1,
                deprecated_posargs=(-1, 0, False),
            )
