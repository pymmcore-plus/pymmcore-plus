"""pymmcore superset providing improved APIs, event handling, and a pure python acquisition engine."""  # noqa: E501

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pymmcore-plus")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"


from ._accumulator import AbstractChangeAccumulator, get_device_accumulator
from ._logger import configure_logging
from ._util import find_micromanager, use_micromanager
from .core import (
    CFGCommand,
    CFGGroup,
    CMMCorePlus,
    ConfigGroup,
    Configuration,
    Device,
    DeviceAdapter,
    DeviceDetectionStatus,
    DeviceInitializationState,
    DeviceNotification,
    DeviceProperty,
    DeviceType,
    FocusDirection,
    Keyword,
    Metadata,
    PixelFormat,
    PortType,
    PropertyType,
)
from .core.events import CMMCoreSignaler, PCoreSignaler
from .mda._runner import GeneratorMDASequence

__all__ = [
    "AbstractChangeAccumulator",
    "ActionType",
    "CFGCommand",
    "CFGGroup",
    "CMMCorePlus",
    "CMMCoreSignaler",
    "ConfigGroup",
    "Configuration",
    "Device",
    "DeviceAdapter",
    "DeviceDetectionStatus",
    "DeviceInitializationState",
    "DeviceNotification",
    "DeviceProperty",
    "DeviceType",
    "FocusDirection",
    "GeneratorMDASequence",
    "Keyword",
    "Metadata",
    "PCoreSignaler",
    "PixelFormat",
    "PortType",
    "PropertyType",
    "__version__",
    "configure_logging",
    "find_micromanager",
    "get_device_accumulator",
    "use_micromanager",
]
