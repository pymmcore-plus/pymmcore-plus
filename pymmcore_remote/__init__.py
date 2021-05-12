try:
    from ._version import version as __version__
except ImportError:
    __version__ = "unknown"

from ._client import RemoteMMCore
from ._mmcore_plus import CMMCorePlus

__all__ = ["RemoteMMCore", "CMMCorePlus"]
