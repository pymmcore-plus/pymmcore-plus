"""pymmcore superset providing improved APIs, event handling, and a pure python acquisition engine."""  # noqa: E501

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pymmcore-plus")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"


from useq.experimental._runner import GeneratorMDASequence

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
    "PixelFormat",
    "PortType",
    "PropertyType",
    "use_micromanager",
]
