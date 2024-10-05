from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pymmcore_plus.core import CMMCorePlus

    from ._prop_event_mixin import _C


class _DevicePropValueSignal:
    def __init__(
        self, device_label: str, property_name: str | None, mmcore: CMMCorePlus
    ) -> None:
        self._dev = device_label
        self._prop = property_name
        self._mmc = mmcore

    def connect(self, callback: _C) -> _C:
        sig = self._mmc.events.devicePropertyChanged(self._dev, self._prop)
        return sig.connect(callback)  # type: ignore

    def disconnect(self, callback: _C | None = None) -> None:
        sig = self._mmc.events.devicePropertyChanged(self._dev, self._prop)
        sig.disconnect(callback)

    def emit(self, *args: Any) -> Any:
        """Emits the signal with the given arguments."""
        self._mmc.events.devicePropertyChanged(self._dev, self._prop).emit(*args)

    def __call__(self, property: str) -> _DevicePropValueSignal:
        return _DevicePropValueSignal(self._dev, property, self._mmc)
