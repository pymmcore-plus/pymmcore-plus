from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    cast,
)

from psygnal._signal import _normalize_slot
from pymmcore import g_Keyword_Label, g_Keyword_State
from typing_extensions import TypedDict

from ._constants import DeviceType, PropertyType

if TYPE_CHECKING:
    from psygnal._signal import NormedCallback

    from ._mmcore_plus import CMMCorePlus


def _denorm_slot(slot: NormedCallback) -> Optional[Callable]:
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


class InfoDict(TypedDict):
    valid: bool
    value: Optional[Any]
    type: Optional[str]
    device_type: Optional[str]
    read_only: Optional[bool]
    sequenceable: Optional[bool]
    sequence_max_length: Optional[int]
    pre_init: Optional[bool]
    range: Optional[Tuple[float, float]]
    allowed_values: Optional[Tuple[str, ...]]


T = TypeVar("T", bound=Callable[[Any], Any])


class PropertySignal:
    def __init__(
        self,
        dev: Union[str, DeviceProperty],
        prop: Optional[str] = None,
        mmc: Optional[CMMCorePlus] = None,
    ) -> None:
        from ._mmcore_plus import CMMCorePlus

        if isinstance(dev, DeviceProperty):
            prop, mmc = dev.name, dev._mmc
            dev = dev.device
        elif not isinstance(prop, str) and isinstance(mmc, CMMCorePlus):
            raise ValueError(
                "Must provide either a DeviceProperty as the first argument, or "
                "(device: str, property: str, core: CMMCorePlus)"
            )

        self._dev = dev
        self._prop = cast(str, prop)
        self._mmc = cast(CMMCorePlus, mmc)
        self._refs: Dict[NormedCallback, Callable] = {}

    def connect(self, callback: T) -> T:
        slot = _normalize_slot(callback)

        def _wrapper(dev, prop, new_value):
            cb = _denorm_slot(slot)
            if cb is None:
                self._refs.pop(slot)
                return
            if dev == self._dev and prop == self._prop:
                cb(new_value)

        self._refs[slot] = _wrapper
        self._mmc.events.propertyChanged.connect(_wrapper)
        return callback

    def disconnect(self, callback: T):
        slot = _normalize_slot(callback)
        if slot not in self._refs:
            raise ValueError("callback not connected")

        self._mmc.events.propertyChanged.disconnect(self._refs.pop(slot))


class DeviceProperty:
    """Convenience "View" onto a device property.

    Parameters
    ----------
    device_label : str
        Device this property belongs to
    property_name : str
        Name of this property
    mmcore : CMMCorePlus
        CMMCorePlus instance

    Examples
    --------

    >>> core = CMMCorePlus()
    >>> prop = DeviceProperty('Objective', 'Label', core)
    >>> prop.isValid()  # points to a loaded device property in core
    >>> prop.value
    >>> prop.value = 'Objective-2'  # setter
    >>> prop.isReadOnly()
    >>> prop.hasLimits()
    >>> prop.range()
    >>> prop.dict()  # all the info in one dict.
    """

    def __init__(
        self, device_label: str, property_name: str, mmcore: CMMCorePlus
    ) -> None:

        self.device = device_label
        self.name = property_name
        self._mmc = mmcore
        self.valueChanged = PropertySignal(self)

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

    def fromCache(self) -> Any:
        """Return cached property value."""
        return self._mmc.getPropertyFromCache(self.device, self.name)

    def setValue(self, val: Any) -> None:
        """Functional alternate to property setter."""
        if self.isReadOnly():
            import warnings

            warnings.warn(f"'{self.device}::{self.name}' is a read-only property.")
        try:
            self._mmc.setProperty(self.device, self.name, val)
        except RuntimeError as e:
            msg = str(e)
            if allowed := self.allowedValues():
                msg += f". Allowed values: {allowed}"
            raise RuntimeError(msg) from None

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

    def isSequenceable(self) -> bool:
        """Return `True` if property can be used in a sequence."""
        return self._mmc.isPropertySequenceable(self.device, self.name)

    def sequenceMaxLength(self) -> int:
        """Return maximum number of property events that can be put in a sequence"""
        return self._mmc.getPropertySequenceMaxLength(self.device, self.name)

    def loadSequence(self, eventSequence: Sequence[str]) -> None:
        """Transfer a sequence of events/states/whatever to the device.

        Parameters
        ----------
        eventSequence : Sequence[str]
            The sequence of events/states that the device will execute in response
            to external triggers
        """
        self._mmc.loadPropertySequence(self.device, self.name, eventSequence)

    def startSequence(self) -> None:
        """Start an ongoing sequence of triggered events in a property."""
        self._mmc.startPropertySequence(self.device, self.name)

    def stopSequence(self) -> None:
        """Stop an ongoing sequence of triggered events in a property."""
        self._mmc.stopPropertySequence(self.device, self.name)

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
                "sequenceable": self.isSequenceable(),
                "sequence_max_length": (
                    self.sequenceMaxLength() if self.isSequenceable() else None
                ),
                "pre_init": self.isPreInit(),
                "range": self.range() if self.hasLimits() else None,
                "allowed_values": self.allowedValues(),
            }
        else:
            return {
                "valid": False,
                "value": None,
                "type": None,
                "device_type": None,
                "read_only": None,
                "sequenceable": None,
                "sequence_max_length": None,
                "pre_init": None,
                "range": None,
                "allowed_values": None,
            }

    InfoDict = InfoDict

    def __repr__(self) -> str:
        v = f"value={self.value!r}" if self.isValid() else "INVALID"
        core = repr(self._mmc).strip("<>")
        return f"<Property '{self.device}::{self.name}' on {core}: {v}>"
