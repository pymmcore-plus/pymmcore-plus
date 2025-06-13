from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    Literal,
    TypeVar,
    Union,
    cast,
    overload,
)

from pymmcore_plus.core._constants import PropertyType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from typing_extensions import Self, TypeAlias

    from ._device_base import Device

    PropArg: TypeAlias = (
        PropertyType | type | Literal["float", "integer", "string", "boolean"] | None
    )

TDev = TypeVar("TDev", bound="Device")
TProp = TypeVar("TProp")
TLim = TypeVar("TLim", bound=Union[int, float])


slots_true = {"slots": True} if sys.version_info >= (3, 10) else {}
kw_only_true = {"kw_only": True} if sys.version_info >= (3, 10) else {}


@dataclass(**kw_only_true, **slots_true)
class PropertyInfo(Generic[TProp]):
    """State of a property of a device.

    Attributes
    ----------
    name : str
        The name of the property.
    default_value : TProp, optional
        The default value of the property, by default None.
    last_value : TProp, optional
        The last value seen from the device, by default None.
    limits : tuple[int | float, int | float], optional
        The minimum and maximum values of the property, by default None.
    sequence_max_length : int
        The maximum length of a sequence of property values.
    description : str, optional
        A description of the property, by default None.
    type : PropertyType
        The type of the property.
    allowed_values : Sequence[TProp], optional
        The allowed values of the property, by default None.
    is_read_only : bool
        Whether the property is read-only.
    is_pre_init : bool
        Whether the property must be set before initialization.
    """

    name: str
    default_value: TProp | None = None  # could be used for a "reset"?
    last_value: TProp | None = None  # the last value we saw from the device
    limits: tuple[int | float, int | float] | None = None
    sequence_max_length: int = 0
    description: str | None = None
    type: PropertyType = PropertyType.Undef

    allowed_values: Sequence[TProp] | None = None
    is_read_only: bool | None = None
    is_pre_init: bool = False

    @property
    def number_of_allowed_values(self) -> int:
        """Return the number of allowed values."""
        if self.allowed_values is None:
            return 0
        return len(self.allowed_values)

    @property
    def is_sequenceable(self) -> bool:
        """Return True if the property is sequenceable."""
        return self.sequence_max_length > 0

    def __post_init__(self) -> None:
        """Ensure sound property configuration."""
        if self.allowed_values and self.limits:  # pragma: no cover
            raise ValueError(
                f"Property {self.name!r} cannot have both allowed values and limits. "
                "Please choose one or the other."
            )

    def __setattr__(self, name: str, value: Any) -> None:
        """Perform additional checks when setting attributes."""
        object.__setattr__(self, name, value)  # slots dataclass has no super()...
        # setting allowed values also removes the limits
        if name == "allowed_values" and value is not None:
            self.limits = None


class PropertyController(Generic[TDev, TProp]):
    """Controls the state of a property connected to a device.

    PropertyController instances are descriptors (i.e. they behave like @property),
    that can get and set the value of a property on a Device instance using the
    getter and setter methods provided at initialization.  They can also load and
    start sequences of property values, if the property is sequenceable (i.e. it has
    a non-zero sequence_max_length and has been provided with `sequence_loader` and
    `sequence_starter` methods).

    Device subclasses maintain PropertyController instances in a ClassVar dictionary,
    `_prop_controllers`, where the keys are the property names and the values are the
    PropertyController instances.
    """

    def __init__(
        self,
        property: PropertyInfo[TProp],
        fget: Callable[[TDev], TProp] | None = None,
        fset: Callable[[TDev, TProp], None] | None = None,
        fseq_load: Callable[[TDev, Sequence[TProp]], None] | None = None,
        fseq_start: Callable[[TDev], None] | None = None,
        fseq_stop: Callable[[TDev], None] | None = None,
        doc: str | None = None,
    ) -> None:
        self.property = property
        self.fget = fget
        self.fset = fset
        self.fseq_load = fseq_load
        self.fseq_start = fseq_start
        self.fseq_stop = fseq_stop
        self.doc = doc

    # same as "Property::Update" in CMMCore
    @overload
    def __get__(
        self, instance: None, owner: type[TDev]
    ) -> PropertyController[TDev, TProp]: ...
    @overload
    def __get__(self, instance: TDev, owner: type[TDev]) -> TProp: ...
    def __get__(
        self, instance: TDev | None, owner: type[TDev]
    ) -> TProp | PropertyController[TDev, TProp]:
        """Update the property value by calling the getter on the Device instance."""
        if instance is None:  # pragma: no cover
            return self
        if self.fget is None:  # pragma: no cover
            raise AttributeError("Unreadable property")
        val = self.fget(instance)  # cache the value
        object.__setattr__(self.property, "last_value", val)
        return val

    # same as "Property::Apply" in CMMCore
    def __set__(self, instance: TDev, value: TProp) -> None:
        """Update the property value by calling the setter on the Device instance."""
        if self.fset is None:  # pragma: no cover
            raise AttributeError("Unsettable property")
        value = self.validate(value)
        self.fset(instance, value)

    def validate(self, value: Any) -> TProp:
        """Validate a property value."""
        if self.property.allowed_values and value not in self.property.allowed_values:
            raise ValueError(
                f"Value '{value}' is not allowed for property '{self.property.name}'. "
                f"Allowed values: {list(self.property.allowed_values)}."
            )
        if self.property.limits:
            try:
                value = float(value)
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"Non-numeric value {value!r} cannot be compared to the limits "
                    f"of property {self.property.name!r}: {self.property.limits}."
                ) from e
            min_, max_ = self.property.limits
            if not min_ <= cast("float", value) <= max_:
                raise ValueError(
                    f"Value {value!r} is not within the allowed range of property "
                    f"{self.property.name!r}: {self.property.limits}."
                )
        return cast("TProp", value)

    @property
    def is_sequenceable(self) -> bool:
        """Return True if the property is sequenceable."""
        return (
            self.property.is_sequenceable
            and self.fseq_load is not None
            and self.fseq_start is not None
        )

    @property
    def is_read_only(self) -> bool:
        """Return True if the property is read-only.

        We consider a property read-only either if the device has explicitly set it as
        such, or if the property has a getter but no setter.
        If it has *neither* a getter nor a setter, and is not explicitly marked as
        read-only, it is considered writeable: this is assumed to be a "configuration"
        property that the device adapter cares about, but which is likely never sent
        to the device itself.
        """
        return self.property.is_read_only is True or (
            self.fset is None and self.fget is not None
        )

    def load_sequence(self, instance: TDev, sequence: Sequence[TProp]) -> None:
        """Send a sequence of property values to the device."""
        if self.fseq_load is None:
            raise RuntimeError(
                f"Property {self.property.name!r} is not sequenceable. "
                "No sequence loader is defined."
            )
        if (seq_len := len(sequence)) > (max_len := self.property.sequence_max_length):
            raise ValueError(
                f"Sequence length {seq_len} exceeds the maximum allowed length "
                f"of property {self.property.name!r}: {max_len}."
            )
        seq = [self.validate(val) for val in sequence]
        self.fseq_load(instance, seq)

    def start_sequence(self, instance: TDev) -> None:
        """Tell the device to start the previously loaded sequence."""
        if self.fseq_start is None:
            raise RuntimeError(
                f"Property {self.property.name!r} is not sequenceable. "
                "No sequence starter is defined."
            )
        self.fseq_start(instance)

    def stop_sequence(self, instance: TDev) -> None:
        """Stop the sequence."""
        # it's not an error if there is no stopper
        if self.fseq_stop is not None:
            self.fseq_stop(instance)

    # ------------------------- Decorators -------------------------

    def setter(self, fset: Callable[[TDev, TProp], None]) -> Self:
        """Decorate a method to set the property on the device."""
        self.fset = fset
        if self.property.is_read_only is None:
            self.property.is_read_only = False
        return self

    def sequence_loader(
        self, fseq_load: Callable[[TDev, Sequence[TProp]], None]
    ) -> Self:
        """Decorate a method that sends a property value sequence to the device."""
        self.fseq_load = fseq_load
        return self

    def sequence_starter(self, fseq_start: Callable[[TDev], None]) -> Self:
        """Decorate a method that starts a (previously loaded) property sequence."""
        self.fseq_start = fseq_start
        return self

    def sequence_stopper(self, fseq_stop: Callable[[TDev], None]) -> Self:
        """Decorate a method that stops the currently running property sequence."""
        self.fseq_stop = fseq_stop
        return self


@overload  # when used as a decorator
def pymm_property(fget: Callable[[TDev], TProp]) -> PropertyController[TDev, TProp]: ...
@overload  # when used with keyword arguments including allowed_values
def pymm_property(
    *,
    allowed_values: Sequence[TProp] | None,  # cannot be combined with limits
    sequence_max_length: int = ...,
    is_read_only: bool | None = ...,
    is_pre_init: bool = ...,
    name: str | None = ...,
    property_type: PropArg = ...,
) -> Callable[[Callable[[TDev], TProp]], PropertyController[TDev, TProp]]: ...
@overload  # when used with keyword arguments including limits
def pymm_property(
    *,
    limits: tuple[TLim, TLim] | None,  # cannot be combined with allowed_values
    sequence_max_length: int = ...,
    is_read_only: bool | None = ...,
    is_pre_init: bool = ...,
    name: str | None = ...,
    property_type: PropArg = ...,
) -> Callable[[Callable[[TDev], TLim]], PropertyController[TDev, TLim]]: ...
@overload  # when used with keyword arguments without allowed_values or limits
def pymm_property(
    *,
    sequence_max_length: int = ...,
    is_read_only: bool | None = ...,
    is_pre_init: bool = ...,
    name: str | None = ...,
    property_type: PropArg = ...,
) -> Callable[[Callable[[TDev], TProp]], PropertyController[TDev, TProp]]: ...
def pymm_property(
    fget: Callable[[TDev], TProp] | None = None,
    *,
    limits: tuple[TLim, TLim] | None = None,
    sequence_max_length: int = 0,
    allowed_values: Sequence[TProp] | None = None,
    is_read_only: bool | None = None,
    is_pre_init: bool = False,
    name: str | None = None,  # taken from fget if None
    property_type: PropArg = None,
) -> (
    PropertyController[TDev, TProp]
    | Callable[[Callable[[TDev], TProp]], PropertyController[TDev, TProp]]
):
    """Decorates a (getter) method to create a device property.

    The returned PropertyController instance can be additionally used (similar to
    `@property`) to decorate `setter`, `sequence_loader`, `sequence_starter`, and/or
    `sequence_stopper` methods.

    Properties can have limits, allowed values, but may not have both.

    Properties will only be considered "sequenceable" (i.e. they support hardware
    triggering) if they have a non-zero sequence_max_length AND have decorated
    `sequence_loader` and `sequence_starter` methods.

    Parameters
    ----------
    fget : Callable[[TDev], TProp], optional
        The getter method for the property, by default None.
    limits : tuple[float, float], optional
        The minimum and maximum values of the property, by default None. Cannot be
        combined with `allowed_values`.
    sequence_max_length : int, optional
        The maximum length of a sequence of property values, by default 0.
    allowed_values : Sequence[TProp], optional
        The allowed values of the property, by default None. Cannot be combined with
        `limits`.
    is_read_only : bool, optional
        Whether the property is read-only, by default False.
    is_pre_init : bool, optional
        Whether the property must be set before initialization, by default False.
    name : str, optional
        The name of the property, by default, the name of the getter method is used.
    prop_type : PropArg, optional
        The type of the property, by default the return annotation of the getter method
        is used (but must be one of `float`, `int`, or `str`).


    Examples
    --------
    ```python
    class MyDevice(Device):
        @pymm_property(limits=(0, 100), sequence_max_length=10)
        def position(self) -> float:
            # get position from device
            return 42.0

        @position.setter
        def position(self, value: float) -> None:
            print(f"Setting position to {value}")

        @position.sequence_loader
        def load_position_sequence(self, sequence: Sequence[float]) -> None:
            print(f"Loading position sequence: {sequence}")

        @position.sequence_starter
        def start_position_sequence(self) -> None:
            print("Starting position sequence")

        @pymm_property(is_read_only=True)
        def pressure(self) -> float:
            return 1.0

        @pymm_property(allowed_values=["low", "medium", "high"])
        def speed(self) -> str:
            # get speed from device
            return "medium"

        @speed.setter
        def speed(self, value: str) -> None:
            print(f"Setting speed to {value}")
    ```
    """

    def _inner(
        fget: Callable[[TDev], TProp], _pt: PropArg = property_type
    ) -> PropertyController[TDev, TProp]:
        prop = PropertyInfo(
            name=name or fget.__name__,
            description=fget.__doc__,
            limits=limits,
            sequence_max_length=sequence_max_length,
            allowed_values=allowed_values,
            # all @pymm_property properties are read-only by default
            # until they are decorated with a setter
            # this does not apply to properties that are manually registered
            # with Device.register_property.
            is_read_only=is_read_only,
            is_pre_init=is_pre_init,
            type=PropertyType.create(_pt or fget.__annotations__.get("return", None)),
        )

        return PropertyController(property=prop, fget=fget)

    return _inner if fget is None else _inner(fget)
