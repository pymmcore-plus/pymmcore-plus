from __future__ import annotations

from typing import TYPE_CHECKING

from ..._util import _qt_app_is_running
from ._protocol import PMDASignaler
from ._psygnal import MDASignaler

if TYPE_CHECKING:
    from ._qsignals import QMDASignaler


__all__ = [
    "PMDASignaler",
    "MDASignaler",
    "QMDASignaler",
    "_get_auto_MDA_callback_class",
]


def _get_auto_MDA_callback_class(
    default: type[PMDASignaler] = MDASignaler,  # type: ignore
) -> type[PMDASignaler]:
    if _qt_app_is_running():
        from ._qsignals import QMDASignaler

        return QMDASignaler

    return default


def __dir__() -> list[str]:
    return [*list(globals()), "QMDASignaler"]


def __getattr__(name: str) -> object:
    if name == "QMDASignaler":
        try:
            from ._qsignals import QMDASignaler

            return QMDASignaler
        except ImportError as e:
            raise ImportError(
                f"{e}.\nQMDASignaler requires qtpy and either PySide2 or PyQt5.`"
            ) from e

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
