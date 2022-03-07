from typing import Any, Optional, Tuple

from pymmcore import g_Keyword_Label, g_Keyword_State

from ._constants import DeviceType, PropertyType
from ._mmcore_plus import CMMCorePlus


class MMProperty:
    """Convenience "View" onto a device property.

    Parameters
    ----------
    device_label : str
        Device this property belongs to
    property_name : str
        Name of this property
    mmcore : Optional[CMMCorePlus]
        CMMCore instance, by default global singleton.

    Examples
    --------

    >>> prop = MMProperty('Objective', 'Label')
    >>> prop.dict()
    >>> prop.core.loadSystemConfiguration()
    >>> prop.dict()
    >>> prop.value
    >>> prop.value = 'Objective-2'
    >>> prop.isReadOnly()
    >>> prop.hasLimits()
    >>> prop.range()
    ...
    """

    def __init__(
        self,
        device_label: str,
        property_name: str,
        *,
        mmcore: Optional[CMMCorePlus] = None,
    ) -> None:

        self.device = device_label
        self.name = property_name
        self._mmc = mmcore or CMMCorePlus.instance()

    def isValid(self) -> bool:
        return self.isLoaded() and self._mmc.hasProperty(self.device, self.name)

    def isLoaded(self) -> bool:
        return self._mmc is not None and self.device in self._mmc.getLoadedDevices()

    @property
    def core(self) -> CMMCorePlus:
        return self._mmc

    @core.setter
    def core(self, mmcore: CMMCorePlus) -> None:
        self._mmc = mmcore

    # functional alternate to property setter
    def setCore(self, mmcore: CMMCorePlus) -> None:
        self._mmc = mmcore

    @property
    def value(self) -> Any:
        """Return value, cast to appropriate type if applicable."""
        v = self._mmc.getProperty(self.device, self.name)
        if type_ := self.type().to_python():
            v = type_(v)
        return v

    @value.setter
    def value(self, val: Any) -> None:
        self.setValue(val)

    # functional alternate to property setter
    def setValue(self, val: Any) -> None:
        if self.isReadOnly():
            import warnings

            warnings.warn(f"'{self.device}::{self.name}' is a read-only property.")
        self._mmc.setProperty(self.device, self.name, val)

    def isReadOnly(self) -> bool:
        return self._mmc.isPropertyReadOnly(self.device, self.name)

    def isPreInit(self) -> bool:
        return self._mmc.isPropertyPreInit(self.device, self.name)

    def hasLimits(self) -> bool:
        return self._mmc.hasPropertyLimits(self.device, self.name)

    def lowerLimit(self) -> float:
        return self._mmc.getPropertyLowerLimit(self.device, self.name)

    def upperLimit(self) -> float:
        return self._mmc.getPropertyUpperLimit(self.device, self.name)

    def range(self) -> Tuple[float, float]:
        return (self.lowerLimit(), self.upperLimit())

    def type(self) -> PropertyType:
        return self._mmc.getPropertyType(self.device, self.name)

    def deviceType(self) -> DeviceType:
        return self._mmc.getDeviceType(self.device)

    def allowedValues(self) -> Tuple[str, ...]:
        # https://github.com/micro-manager/mmCoreAndDevices/issues/172
        allowed = self._mmc.getAllowedPropertyValues(self.device, self.name)
        if not allowed and self.deviceType() is DeviceType.StateDevice:
            if self.name == g_Keyword_State:
                n_states = self._mmc.getNumberOfStates(self.device)
                allowed = tuple(str(i) for i in range(n_states))
            elif self.name == g_Keyword_Label:
                allowed = self._mmc.getStateLabels(self.device)
        return allowed

    def dict(self) -> dict:
        d = {
            "valid": self.isValid(),
            "value": None,
            "type": None,
            "device_type": None,
            "read_only": None,
            "pre_init": None,
            "range": None,
            "allowed": None,
        }

        if d["valid"]:
            d["value"] = self.value
            d["type"] = self.type().to_json()
            d["device_type"] = self.deviceType().name
            d["read_only"] = self.isReadOnly()
            d["pre_init"] = self.isPreInit()
            d["range"] = self.range() if self.hasLimits() else None
            d["allowed"] = self.allowedValues()
        return d

    def __repr__(self) -> str:
        v = f"value={self.value!r}" if self.isValid() else "INVALID"
        return f"<Property {self.name} on device {self.device}: {v}>"
