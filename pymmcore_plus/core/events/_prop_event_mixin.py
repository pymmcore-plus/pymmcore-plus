from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

from psygnal._signal import NormedCallback, _normalize_slot

from ._protocol import PCoreSignaler

_C = TypeVar("_C", bound=Callable[[Any], Any])
PropKey = Tuple[str, Optional[str], NormedCallback]
PropKeyDict = Dict[PropKey, Callable]


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


class _PropertySignal:
    def __init__(
        self,
        core_events: "_DevicePropertyEventMixin",
        device: str,
        property: Optional[str] = None,
    ) -> None:
        self._events = core_events
        self._device = device
        self._property = property

    def connect(self, callback: _C) -> _C:
        slot = _normalize_slot(callback)
        key = (self._device, self._property, slot)

        def _wrapper(dev, prop, new_value):
            cb = _denormalize_slot(slot)
            if cb is None:
                self._events._prop_callbacks.pop(key)
                return
            if dev == self._device and (not self._property or prop == self._property):
                cb(new_value)

        self._events._prop_callbacks[key] = _wrapper
        self._events.propertyChanged.connect(_wrapper)
        return callback

    def disconnect(self, callback: Callable) -> None:
        key = (self._device, self._property, _normalize_slot(callback))
        if key not in self._events._prop_callbacks:
            raise ValueError("callback not connected")
        self._events.propertyChanged.disconnect(self._events._prop_callbacks.pop(key))


class _DevicePropertyEventMixin(PCoreSignaler):
    _prop_callbacks: PropKeyDict = {}

    def devicePropertyEvent(
        self, device_label: str, property_label: Optional[str] = None
    ) -> _PropertySignal:
        return _PropertySignal(self, device_label, property_label)
