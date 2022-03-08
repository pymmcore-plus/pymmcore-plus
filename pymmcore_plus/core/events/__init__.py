from typing import TYPE_CHECKING, Callable, Optional

from psygnal._signal import _normalize_slot

from ..._util import _qt_app_is_running
from ._protocol import PCoreSignaler
from ._psygnal import CMMCoreSignaler

if TYPE_CHECKING:
    from psygnal._signal import NormedCallback

    from ._qsignals import QCoreSignaler

__all__ = [
    "CMMCoreSignaler",
    "QCoreSignaler",
    "PCoreSignaler",
    "_get_auto_core_callback_class",
    "_normalize_slot",
    "_denormalize_slot",
]


def _get_auto_core_callback_class(default=CMMCoreSignaler):
    if _qt_app_is_running():
        from ._qsignals import QCoreSignaler

        return QCoreSignaler

    return default


def _denormalize_slot(slot: "NormedCallback") -> Optional[Callable]:
    if not isinstance(slot, tuple):
        return slot

    _ref, name, method = slot
    obj = _ref()
    if obj is None:
        return None
    if method is not None:
        return method
    _cb = getattr(obj, name, None)
    if _cb is None:  # pragma: no cover
        return None
    return _cb


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
