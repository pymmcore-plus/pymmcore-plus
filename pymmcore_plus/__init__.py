try:
    from ._version import version as __version__
except ImportError:  # pragma: no cover
    __version__ = "unknown"

from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from .remote import RemoteMMCore, server

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
    "server",
    "CMMCorePlus",
    "find_micromanager",
]


def __dir__():
    return __all__


def __getattr__(name: str):
    try:
        if name == "RemoteMMCore":
            from .remote import RemoteMMCore

            return RemoteMMCore
        if name == "server":
            from .remote import server

            return server
    except ImportError as e:
        raise ImportError(
            f"{e}.\nTo use the interprocess features of pymmcore-plus, "
            "please install with `pip install pymmcore-plus[remote]`"
        ) from e

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
