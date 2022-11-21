from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .. import CMMCorePlus

from ._prop_event_mixin import _C


class _DevicePropValueSignal:
    def __init__(
        self, device_label: str, property_name: Optional[str], mmcore: "CMMCorePlus"
    ) -> None:
        self._dev = device_label
        self._prop = property_name
        self._mmc = mmcore

    def connect(self, callback: _C) -> _C:
        return self._mmc.events.devicePropertyChanged(self._dev, self._prop).connect(
            callback
        )

    def disconnect(self, callback: _C):
        return self._mmc.events.devicePropertyChanged(self._dev, self._prop).disconnect(
            callback
        )

    def __call__(self, property: str):
        return _DevicePropValueSignal(self._dev, property, self._mmc)
