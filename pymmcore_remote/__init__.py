try:
    from ._version import version as __version__
except ImportError:
    __version__ = "unknown"

from ._client import remote_mmcore

__all__ = ["remote_mmcore"]
