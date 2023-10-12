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
from .mda._runner import EventIterable

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
    "DeviceNotification",
    "DeviceProperty",
    "DeviceType",
    "find_micromanager",
    "FocusDirection",
    "EventIterable",
    "Keyword",
    "Metadata",
    "PCoreSignaler",
    "PortType",
    "PropertyType",
]
