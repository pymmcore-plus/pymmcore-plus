try:
    from ._version import version as __version__
except ImportError:
    __version__ = "unknown"

from typing import TYPE_CHECKING, Any, List

from ._util import find_micromanager
from .core import (
    ActionType,
    CMMCorePlus,
    ConfigGroup,
    Configuration,
    Device,
    DeviceDetectionStatus,
    DeviceNotification,
    DeviceProperty,
    DeviceType,
    FocusDirection,
    Metadata,
    PortType,
    PropertyType,
)
from .core.events import CMMCoreSignaler, PCoreSignaler
from .mda._runner import GeneratorMDASequence

if TYPE_CHECKING:
    from .remote import RemoteMMCore, server

__all__ = [
    "__version__",
    "ActionType",
    "CMMCorePlus",
    "CMMCoreSignaler",
    "ConfigGroup",
    "Configuration",
    "Device",
    "DeviceDetectionStatus",
    "DeviceNotification",
    "DeviceProperty",
    "DeviceType",
    "find_micromanager",
    "FocusDirection",
    "GeneratorMDASequence",
    "Metadata",
    "PCoreSignaler",
    "PortType",
    "PropertyType",
    "RemoteMMCore",
    "server",
]


def __dir__() -> List[str]:
    return [*list(globals()), "RemoteMMCore", "server"]


def __getattr__(name: str) -> Any:
    if name in {"RemoteMMCore", "server"}:
        try:
            from . import remote

            return getattr(remote, name)
        except ImportError as e:
            raise ImportError(
                f"{e}.\nTo use the interprocess features of pymmcore-plus, "
                "please install with `pip install pymmcore-plus[remote]`"
            ) from e

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
