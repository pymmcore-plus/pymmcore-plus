try:
    from ._version import version as __version__
except ImportError:  # pragma: no cover
    __version__ = "unknown"

from .client import RemoteMMCore
from .core import CMMCorePlus

__all__ = ["RemoteMMCore", "CMMCorePlus"]
