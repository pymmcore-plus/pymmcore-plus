from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

from psygnal._signal import NormedCallback, _normalize_slot

from ._protocol import PCoreSignaler

_C = TypeVar("_C", bound=Callable[..., Any])
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
        """Connect callback to this device and/or property.

        If only `device` was provided, the callback must take *two* parameters
        (property_name, new_value). If both `device` and `property` were provided, the
        callback must take *one* parameter (new_value).

        Parameters
        ----------
        callback : Callable
            If only `device` was provided, the callback must take *two* parameters
            (property_name, new_value). If both `device` and `property` were provided,
            the callback must take *one* parameter (new_value).

        Returns
        -------
        callback
            the callback is returned for use as a decorator.
        """
        slot = _normalize_slot(callback)
        key = (self._device, self._property, slot)

        def _wrapper(dev, prop, new_value):
            cb = _denormalize_slot(slot)
            if cb is None:
                self._events._prop_callbacks.pop(key)
                return
            if dev == self._device:
                if self._property:
                    if prop == self._property:
                        cb(new_value)
                else:
                    cb(prop, new_value)

        self._events._prop_callbacks[key] = _wrapper
        self._events.propertyChanged.connect(_wrapper)
        return callback

    def disconnect(self, callback: Callable) -> None:
        """Disconnect `callback` from this device and/or property."""
        key = (self._device, self._property, _normalize_slot(callback))
        if key not in self._events._prop_callbacks:
            raise ValueError("callback not connected")
        self._events.propertyChanged.disconnect(self._events._prop_callbacks.pop(key))


class _DevicePropertyEventMixin(PCoreSignaler):
    _prop_callbacks: PropKeyDict = {}

    def devicePropertyChanged(
        self, device: str, property: Optional[str] = None
    ) -> _PropertySignal:
        """Return object to connect/disconnect to device/property-specific changes.

        Note that the callback provided to `.connect()` must take *two* parameters
        (property_name, new_value) if only `device` is provided, and *one* parameter
        (new_value) of both `device` and `property` are provided.

        Parameters
        ----------
        device : str
            A device label
        property : Optional[str]
            Optional property label.  If not provided, all property changes on `device`
            will trigger an event emission. by default None

        Returns
        -------
        _PropertySignal
            Object with `connect` and `disconnect` methods that attach a callback to
            the change event of a specific property or device.

        Examples
        --------
        >>> core.events.devicePropertyChanged('Camera', 'Gain').connect(callback)
        >>> core.events.devicePropertyChanged('Camera').connect(callback)
        """
        return _PropertySignal(self, device, property)
