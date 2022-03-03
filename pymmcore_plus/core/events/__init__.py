import sys

from ._psygnal import CMMCoreSignaler

__all__ = ["CMMCoreSignaler", "_get_auto_callback_class"]


def _get_auto_callback_class():
    for modname in {"PyQt5", "PySide2", "PyQt6", "PySide6"}:
        if qmodule := sys.modules.get(modname):
            QtWidgets = getattr(qmodule, "QtWidgets")
            if QtWidgets.QApplication.instance() is not None:
                from .qcallback import QCoreCallback

                return QCoreCallback

    return CMMCoreSignaler
