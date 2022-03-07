from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Tuple

from pymmcore import g_Keyword_Label, g_Keyword_State

from ._constants import DeviceType, PropertyType

if TYPE_CHECKING:
    from typing_extensions import TypedDict

    from ._mmcore_plus import CMMCorePlus

    class InfoDict(TypedDict):
        valid: bool
        value: Optional[Any]
        type: Optional[str]
        device_type: Optional[str]
        read_only: Optional[bool]
        pre_init: Optional[bool]
        range: Optional[Tuple[float, float]]
        allowed: Optional[Tuple[str, ...]]


class MMProperty:
    """Convenience "View" onto a device property.

    Parameters
    ----------
    mmcore : CMMCore
        CMMCore instance
    device_label : str
        Device this property belongs to
    property_name : str
        Name of this property

    Examples
    --------

    >>> core = CMMCorePlus()
    >>> prop = MMProperty(core, 'Objective', 'Label')
    >>> prop.isValid()  # points to a loaded device property in core
    >>> prop.value
    >>> prop.value = 'Objective-2'  # setter
    >>> prop.isReadOnly()
    >>> prop.hasLimits()
    >>> prop.range()
    >>> prop.dict()  # all the info in one dict.
    """

    def __init__(
        self, mmcore: CMMCorePlus, device_label: str, property_name: str
    ) -> None:

        self.device = device_label
        self.name = property_name
        self._mmc = mmcore

    def isValid(self) -> bool:
        """Return `True` if device is loaded and has a property by this name."""
        return self.isLoaded() and self._mmc.hasProperty(self.device, self.name)

    def isLoaded(self) -> bool:
        """Return true if the device name is loaded"""
        return self._mmc is not None and self.device in self._mmc.getLoadedDevices()

    @property
    def core(self) -> CMMCorePlus:
        """Return the core instance to which this Property is bound."""
        return self._mmc

    @property
    def value(self) -> Any:
        """Return current property value, cast to appropriate type if applicable."""
        v = self._mmc.getProperty(self.device, self.name)
        if type_ := self.type().to_python():
            v = type_(v)
        return v

    @value.setter
    def value(self, val: Any) -> None:
        """Set current property value"""
        self.setValue(val)

    def setValue(self, val: Any) -> None:
        """Functional alternate to property setter."""
        if self.isReadOnly():
            import warnings

            warnings.warn(f"'{self.device}::{self.name}' is a read-only property.")
        self._mmc.setProperty(self.device, self.name, val)

    def isReadOnly(self) -> bool:
        """Return `True` if property is read only."""
        return self._mmc.isPropertyReadOnly(self.device, self.name)

    def isPreInit(self) -> bool:
        """Return `True` if property must be defined prior to initialization."""
        return self._mmc.isPropertyPreInit(self.device, self.name)

    def hasLimits(self) -> bool:
        """Return `True` if property has limits"""
        return self._mmc.hasPropertyLimits(self.device, self.name)

    def lowerLimit(self) -> float:
        """Return lower limit if property has limits, or 0 otherwise."""
        return self._mmc.getPropertyLowerLimit(self.device, self.name)

    def upperLimit(self) -> float:
        """Return upper limit if property has limits, or 0 otherwise."""
        return self._mmc.getPropertyUpperLimit(self.device, self.name)

    def range(self) -> Tuple[float, float]:
        """Return (lowerLimit, upperLimit) range tuple."""
        return (self.lowerLimit(), self.upperLimit())

    def type(self) -> PropertyType:
        """Return `PropertyType` of this property."""
        return self._mmc.getPropertyType(self.device, self.name)

    def deviceType(self) -> DeviceType:
        """Return `DeviceType` of the device owning this property."""
        return self._mmc.getDeviceType(self.device)

    def allowedValues(self) -> Tuple[str, ...]:
        """Return allowed values for this property, if contstrained."""
        # https://github.com/micro-manager/mmCoreAndDevices/issues/172
        allowed = self._mmc.getAllowedPropertyValues(self.device, self.name)
        if not allowed and self.deviceType() is DeviceType.StateDevice:
            if self.name == g_Keyword_State:
                n_states = self._mmc.getNumberOfStates(self.device)
                allowed = tuple(str(i) for i in range(n_states))
            elif self.name == g_Keyword_Label:
                allowed = self._mmc.getStateLabels(self.device)
        return allowed

    def dict(self) -> InfoDict:
        """Return dict of info about this Property.

        Contains the following keys (See `InfoDict` type): "valid", "value", "type",
        "device_type", "read_only", "pre_init", "range", "allowed".
        """
        if self.isValid():
            return {
                "valid": True,
                "value": self.value,
                "type": self.type().to_json(),
                "device_type": self.deviceType().name,
                "read_only": self.isReadOnly(),
                "pre_init": self.isPreInit(),
                "range": self.range() if self.hasLimits() else None,
                "allowed": self.allowedValues(),
            }
        else:
            return {
                "valid": False,
                "value": None,
                "type": None,
                "device_type": None,
                "read_only": None,
                "pre_init": None,
                "range": None,
                "allowed": None,
            }

    def __repr__(self) -> str:
        v = f"value={self.value!r}" if self.isValid() else "INVALID"
        core = repr(self._mmc).strip("<>")
        return f"<Property '{self.device}::{self.name}' on {core}: {v}>"
