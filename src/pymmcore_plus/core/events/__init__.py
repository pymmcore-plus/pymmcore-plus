from typing import TYPE_CHECKING, Any, List, Type

from ..._util import _qt_app_is_running
from ._protocol import PCoreSignaler
from ._psygnal import CMMCoreSignaler

if TYPE_CHECKING:
    from ._qsignals import QCoreSignaler

__all__ = [
    "CMMCoreSignaler",
    "QCoreSignaler",
    "PCoreSignaler",
    "_get_auto_core_callback_class",
    "_denormalize_slot",
]


def _get_auto_core_callback_class(
    default: Type[PCoreSignaler] = CMMCoreSignaler,
) -> Type[PCoreSignaler]:
    if _qt_app_is_running():
        from ._qsignals import QCoreSignaler

        return QCoreSignaler

    return default


def __dir__() -> List[str]:
    return [*list(globals()), "QCoreSignaler"]


def __getattr__(name: str) -> Any:
    if name == "QCoreSignaler":
        try:
            from ._qsignals import QCoreSignaler

            return QCoreSignaler
        except ImportError as e:
            raise ImportError(
                f"{e}.\nQCoreSignaler requires qtpy and either PySide2 or PyQt5.`"
            ) from e

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
