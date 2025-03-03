from typing import TYPE_CHECKING, Any

from pymmcore_plus._util import signals_backend

from ._protocol import PCoreSignaler
from ._psygnal import CMMCoreSignaler

if TYPE_CHECKING:
    from ._qsignals import QCoreSignaler


__all__ = [
    "CMMCoreSignaler",
    "PCoreSignaler",
    "QCoreSignaler",
    "_denormalize_slot",
    "_get_auto_core_callback_class",
]


def _get_auto_core_callback_class() -> type[PCoreSignaler]:
    if signals_backend() == "qt":
        from ._qsignals import QCoreSignaler

        return QCoreSignaler
    return CMMCoreSignaler


def __dir__() -> list[str]:  # pragma: no cover
    return [*list(globals()), "QCoreSignaler"]


def __getattr__(name: str) -> Any:  # pragma: no cover
    if name == "QCoreSignaler":
        try:
            from ._qsignals import QCoreSignaler

            return QCoreSignaler
        except ImportError as e:
            raise ImportError(
                f"{e}.\nQCoreSignaler requires qtpy and a Qt binding."
            ) from e

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
