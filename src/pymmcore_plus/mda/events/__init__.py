from __future__ import annotations

from typing import TYPE_CHECKING

from useq.experimental.protocols import PMDASignaler
from useq.experimental.pysgnals import MDASignaler

from pymmcore_plus import _util

if TYPE_CHECKING:
    from ._qsignals import QMDASignaler  # noqa: TC004


__all__ = [
    "MDASignaler",
    "PMDASignaler",
    "QMDASignaler",
    "_get_auto_MDA_callback_class",
]


def _get_auto_MDA_callback_class() -> type[PMDASignaler]:
    if _util.signals_backend() == "qt":
        from ._qsignals import QMDASignaler

        return QMDASignaler

    # (not sure why this type ignore is needed... apparently isn't matching protocol)
    return MDASignaler  # type: ignore


def __dir__() -> list[str]:  # pragma: no cover
    return [*list(globals()), "QMDASignaler"]


def __getattr__(name: str) -> object:  # pragma: no cover
    if name == "QMDASignaler":
        try:
            from ._qsignals import QMDASignaler

            return QMDASignaler
        except ImportError as e:
            raise ImportError(
                f"{e}.\nQMDASignaler requires qtpy and either PySide2 or PyQt5.`"
            ) from e

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
