"""Bridge support for registering Device properties with the C++ bridge.

The C++ bridge (pymmcore-nano) calls `device.initialize(create_property, notify)`
during device initialization. The `create_property` callable registers MM properties
on the C++ side, and `notify` (DeviceCallbacks) allows sending state-change
notifications to CMMCore.

This module provides `_register_bridge_properties()` which translates our
PropertyController/PropertyInfo system into `create_property()` calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pymmcore_plus.core._constants import PropertyType

if TYPE_CHECKING:
    from collections.abc import Callable

    from ._device_base import Device
    from ._properties import PropertyController

# MM property type enum values (matches MM::PropertyType in C++)
_PROP_TYPE_MAP: dict[PropertyType, int] = {
    PropertyType.Undef: 1,  # MM::String
    PropertyType.String: 1,  # MM::String
    PropertyType.Float: 2,  # MM::Float
    PropertyType.Integer: 3,  # MM::Integer
    PropertyType.Boolean: 1,  # store as string
    PropertyType.Enum: 1,  # store as string
}


def _mm_type(pt: PropertyType) -> int:
    return _PROP_TYPE_MAP.get(pt, 1)


def _parse_string_value(val_str: str, prop_type: PropertyType) -> Any:
    """Parse a string value from C++ back to a typed Python value."""
    if prop_type == PropertyType.Float:
        return float(val_str)
    if prop_type == PropertyType.Integer:
        return int(float(val_str))  # int(float(...)) handles "3.0"
    if prop_type == PropertyType.Boolean:
        return val_str.lower() not in ("0", "false", "")
    return val_str


def _register_bridge_properties(
    device: Device, create_property: Callable[..., Any]
) -> None:
    """Register all device properties with the C++ bridge via create_property().

    Iterates through the device's PropertyControllers and calls create_property()
    for each, creating getter/setter wrappers that convert between typed Python
    values and the string-based C++ property system.
    """
    for _name, ctrl in device._prop_controllers_.items():
        _register_one_property(device, ctrl, create_property)


def _register_one_property(
    device: Device,
    ctrl: PropertyController,
    create_property: Callable[..., Any],
) -> None:
    info = ctrl.property
    prop_type = info.type

    # Default value as string
    if info.default_value is not None:
        default_str = str(info.default_value)
    elif info.last_value is not None:
        default_str = str(info.last_value)
    else:
        default_str = ""

    # Build getter: () -> str
    getter = None
    if ctrl.fget is not None:

        def _getter(_ctrl=ctrl) -> str:
            return str(_ctrl.__get__(device, type(device)))

        getter = _getter

    # Build setter: (str) -> None
    setter = None
    if not ctrl.is_read_only:

        def _setter(val_str: str, _ctrl=ctrl, _pt=prop_type) -> None:
            typed_val = _parse_string_value(val_str, _pt)
            _ctrl.__set__(device, typed_val)

        setter = _setter

    # Limits
    limits = None
    if info.limits is not None:
        limits = (float(info.limits[0]), float(info.limits[1]))

    # Allowed values as strings
    allowed = None
    if info.allowed_values is not None:
        allowed = [str(v) for v in info.allowed_values]

    handle = create_property(
        info.name,
        default_str,
        _mm_type(prop_type),
        ctrl.is_read_only,
        getter=getter,
        setter=setter,
        pre_init=info.is_pre_init,
        limits=limits,
        allowed_values=allowed,
    )
    device._property_handles_[info.name] = handle
