from typing import TYPE_CHECKING

from psygnal import Signal, SignalGroup, SignalInstance

from pymmcore_plus.mda import MDAEngine

from ._deprecated import DeprecatedSignalProxy
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

    # https://github.com/micro-manager/mmCoreAndDevices/pull/659
    imageSnapped = Signal(str)  # on snapImage()
    # when (Continuous)SequenceAcquisition is stopped
    sequenceAcquisitionStopped = Signal(str)
    if TYPE_CHECKING:  # see deprecated impl below
        sequenceAcquisitionStarted = Signal(str)

    # added for CMMCorePlus
    mdaEngineRegistered = Signal(MDAEngine, MDAEngine)
    continuousSequenceAcquisitionStarting = Signal()
    continuousSequenceAcquisitionStarted = Signal()
    if TYPE_CHECKING:
        sequenceAcquisitionStarting = Signal(str)
    autoShutterSet = Signal(bool)
    configGroupDeleted = Signal(str)
    configDeleted = Signal(str, str)
    configDefined = Signal(str, str, str, str, str)
    roiSet = Signal(str, int, int, int, int)

    # aliases for lower casing
    @property
    def xYStagePositionChanged(self) -> SignalInstance:
        return self.XYStagePositionChanged

    @property
    def sLMExposureChanged(self) -> SignalInstance:
        return self.SLMExposureChanged

    if not TYPE_CHECKING:
        _sequenceAcquisitionStarting = Signal(str)
        _sequenceAcquisitionStarted = Signal(str)

        # Deprecated signal wrappers for backwards compatibility
        @property
        def sequenceAcquisitionStarting(self) -> SignalInstance:
            return DeprecatedSignalProxy(
                self._sequenceAcquisitionStarting,
                current_n_args=1,
                deprecated_posargs=(-1, 0, False),
            )

        @property
        def sequenceAcquisitionStarted(self) -> SignalInstance:
            return DeprecatedSignalProxy(
                self._sequenceAcquisitionStarted,
                current_n_args=1,
                deprecated_posargs=(-1, 0, False),
            )
