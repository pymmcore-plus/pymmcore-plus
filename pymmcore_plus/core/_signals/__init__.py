import sys

import numpy as np
from psygnal import Signal, SignalGroup
from useq import MDAEvent, MDASequence

__all__ = [
    "_CMMCoreSignaler",
    "_get_auto_callback_class",
]


class _CMMCoreSignaler(SignalGroup):
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
    sequenceStarted = Signal(MDASequence)  # at the start of an MDA sequence
    sequencePauseToggled = Signal(bool)  # when MDA is paused/unpaused
    sequenceCanceled = Signal(MDASequence)  # when mda is canceled
    sequenceFinished = Signal(MDASequence)  # when mda is done (whether canceled or not)
    frameReady = Signal(np.ndarray, MDAEvent)  # after each event in the sequence
    imageSnapped = Signal(np.ndarray)  # whenever snap is called

    # aliases for lower casing
    @property
    def xYStagePositionChanged(self):
        return self.XYStagePositionChanged

    @property
    def sLMExposureChanged(self):
        return self.SLMExposureChanged


def _get_auto_callback_class():
    for modname in {"PyQt5", "PySide2", "PyQt6", "PySide6"}:
        qmodule = sys.modules.get(modname)
        if qmodule:
            QtWidgets = getattr(qmodule, "QtWidgets")
            if QtWidgets.QApplication.instance() is not None:
                from .qcallback import QCoreCallback

                return QCoreCallback

    return _CMMCoreSignaler
