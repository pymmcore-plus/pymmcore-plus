from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pymmcore-plus")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"


from ._logger import configure_logging
from ._util import find_micromanager
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
    PortType,
    PropertyType,
)
from .core.events import CMMCoreSignaler, PCoreSignaler
from .mda._runner import GeneratorMDASequence

__all__ = [
    "__version__",
    "ActionType",
    "CFGCommand",
    "CFGGroup",
    "CMMCorePlus",
    "CMMCoreSignaler",
    "ConfigGroup",
    "Configuration",
    "configure_logging",
    "Device",
    "DeviceAdapter",
    "DeviceDetectionStatus",
    "DeviceInitializationState",
    "DeviceNotification",
    "DeviceProperty",
    "DeviceType",
    "find_micromanager",
    "FocusDirection",
    "GeneratorMDASequence",
    "Keyword",
    "Metadata",
    "PCoreSignaler",
    "PortType",
    "PropertyType",
]
