try:
    from ._version import version as __version__
except ImportError:  # pragma: no cover
    __version__ = "unknown"

from ._util import find_micromanager
from .core import (
    ActionType,
    CMMCorePlus,
    Configuration,
    DeviceDetectionStatus,
    DeviceNotification,
    DeviceType,
    FocusDirection,
    Metadata,
    PortType,
    PropertyType,
)

__all__ = [
    "ActionType",
    "CMMCorePlus",
    "Configuration",
    "DeviceDetectionStatus",
    "DeviceNotification",
    "DeviceType",
    "FocusDirection",
    "Metadata",
    "PortType",
    "PropertyType",
    "RemoteMMCore",
    "CMMCorePlus",
    "find_micromanager",
]


def __getattr__(name: str):
    if name == "RemoteMMCore":
        try:
            from .remote import RemoteMMCore
        except ImportError as e:
            raise ImportError(
                f"{e}.\nTo use the interprocess features of pymmcore-plus, "
                "please install with `pip install pymmcore-plus[remote]`"
            ) from e

        return RemoteMMCore

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
