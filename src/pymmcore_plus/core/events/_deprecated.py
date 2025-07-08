from __future__ import annotations

import inspect
import warnings
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ._protocol import PSignalInstance


class DeprecatedSignalProxy:
    def __init__(
        self,
        signal: PSignalInstance,
        current_n_args: int,
        deprecated_posargs: tuple[Any, ...],
    ) -> None:
        self._signal = signal
        self._current_n_args = current_n_args
        self._deprecated_posargs = deprecated_posargs
        self._shims: dict[Callable, Callable] = {}

    def connect(self, slot: Callable) -> Any:
        """Connect slot to this signal."""
        min_pos_args = sum(
            1
            for p in inspect.signature(slot).parameters.values()
            if p.kind
            in {
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.POSITIONAL_ONLY,
            }
            and p.default is inspect.Parameter.empty
        )

        num_extra_pos_args = min_pos_args - self._current_n_args
        if num_extra_pos_args > 0:
            extra_args = self._deprecated_posargs[:num_extra_pos_args]
            warnings.warn(
                f"Callback {slot.__name__!r} requires {min_pos_args} positional "
                f"arguments, but this signal only supports {self._current_n_args}. "
                "Fake arguments will be added, but this will be an exception in the "
                "future. Please update your callback.",
                FutureWarning,
                stacklevel=2,
            )

            def _shim(*args: Any) -> Any:
                slot(*args[: self._current_n_args], *extra_args)

            self._shims[slot] = _shim
            self._signal.connect(_shim)
        else:
            self._signal.connect(slot)

    def disconnect(self, slot: Callable | None = None) -> Any:
        """Disconnect slot from this signal.

        If `None`, all slots should be disconnected.
        """
        if slot in self._shims:
            slot = self._shims.pop(slot)
        return self._signal.disconnect(slot)

    def emit(self, *args: Any) -> Any:
        """Emits the signal with the given arguments."""
        return self._signal.emit(*args[: self._current_n_args])
