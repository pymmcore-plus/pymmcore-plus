import sys
from typing import TYPE_CHECKING

from ._protocol import PCoreSignaler
from ._psygnal import CMMCoreSignaler

if TYPE_CHECKING:
    from ._qsignals import QCoreSignaler

__all__ = [
    "CMMCoreSignaler",
    "QCoreSignaler",
    "PCoreSignaler",
    "_get_auto_callback_class",
]


def _get_auto_callback_class(default=CMMCoreSignaler):
    for modname in {"PyQt5", "PySide2", "PyQt6", "PySide6"}:
        if qmodule := sys.modules.get(modname):
            QtWidgets = getattr(qmodule, "QtWidgets")
            if QtWidgets.QApplication.instance() is not None:
                from ._qsignals import QCoreSignaler

                return QCoreSignaler

    return default


def __dir__():
    return list(globals()) + ["QCoreSignaler"]


def __getattr__(name: str):
    if name == "QCoreSignaler":
        try:
            from ._qsignals import QCoreSignaler

            return QCoreSignaler
        except ImportError as e:
            raise ImportError(
                f"{e}.\nQCoreSignaler requires qtpy and either PySide2 or PyQt5.`"
            ) from e

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
