"""pymmcore superset providing improved APIs, event handling, and a pure python acquisition engine."""  # noqa: E501

import logging
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pymmcore-plus")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"


from ._accumulator import AbstractChangeAccumulator
from ._logger import configure_logging
from ._util import find_micromanager, use_micromanager
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
    "use_micromanager",
]


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
