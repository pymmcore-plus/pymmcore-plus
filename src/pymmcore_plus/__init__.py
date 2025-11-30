"""pymmcore superset providing improved APIs, event handling, and a pure python acquisition engine."""  # noqa: E501

import logging
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

try:
    __version__ = version("pymmcore-plus")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"

if TYPE_CHECKING:
    from ._ipy_completion import install_pymmcore_ipy_completion

from ._accumulator import AbstractChangeAccumulator
from ._discovery import find_micromanager, use_micromanager
from ._logger import configure_logging
from .core import (
    ActionType,
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
    "install_pymmcore_ipy_completion",
    "use_micromanager",
]


def __getattr__(name: str) -> Any:
    """Lazy import for compatibility with pymmcore."""
    if name == "install_pymmcore_ipy_completion":
        try:
            from ._ipy_completion import install_pymmcore_ipy_completion
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                f"Error importing IPython completion for pymmcore-plus: {e}"
            ) from None

        return install_pymmcore_ipy_completion
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'. ")


# install the IPython completer when imported, if running in an IPython environment
def _install_ipy_completer() -> None:  # pragma: no cover
    import os
    import sys

    if os.getenv("PYMM_DISABLE_IPYTHON_COMPLETIONS", "0") == "1":
        return
    try:
        if (IPython := sys.modules.get("IPython")) and (shell := IPython.get_ipython()):
            from ._ipy_completion import install_pymmcore_ipy_completion

            install_pymmcore_ipy_completion(shell)
    except Exception as e:
        # If we fail to install the completer, we don't want to crash the import.
        # This is a best-effort installation.
        logging.warning(
            f"Failed to install pymmcore-plus IPython completer:\n  {e}",
        )


_install_ipy_completer()
del _install_ipy_completer
