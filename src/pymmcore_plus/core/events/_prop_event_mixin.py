from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, ClassVar, Dict, Tuple, TypeVar

from ._norm_slot import denormalize_slot, normalize_slot
from ._protocol import PCoreSignaler

if TYPE_CHECKING:
    from ._norm_slot import NormedCallback

    PropKey = Tuple[str, str | None, NormedCallback]
    PropKeyDict = Dict[PropKey, Callable]


_C = TypeVar("_C", bound=Callable[..., Any])


class _PropertySignal:
    def __init__(
        self,
        core_events: _DevicePropertyEventMixin,
        device: str,
        property: str | None = None,
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
        slot = normalize_slot(callback)
        key = (self._device, self._property, slot)

        def _wrapper(dev: str, prop: str, new_value: Any) -> None:
            cb = denormalize_slot(slot)
            if cb is None:
                self._events._prop_callbacks.pop(key, None)
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
        key = (self._device, self._property, normalize_slot(callback))
        cb = self._events._prop_callbacks.pop(key, None)
        if cb is None:
            raise ValueError("callback not connected")
        self._events.propertyChanged.disconnect(cb)

    def emit(self, *args: Any) -> Any:
        raise NotImplementedError("emit not implemented for _PropertySignal")


class _DevicePropertyEventMixin(PCoreSignaler):
    _prop_callbacks: ClassVar[PropKeyDict] = {}

    def devicePropertyChanged(
        self, device: str, property: str | None = None
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
