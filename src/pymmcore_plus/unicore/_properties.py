from __future__ import annotations

from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    TypeVar,
    Union,
    cast,
    overload,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from typing_extensions import Self

    from ._device import Device

TDev = TypeVar("TDev", bound="Device")
TProp = TypeVar("TProp")
TLim = TypeVar("TLim", bound=Union[int, float])


# TODO: maybe use pydantic
@dataclass
class PropertyInfo(Generic[TProp]):
    """State of a property of a device."""

    name: str
    default_value: TProp | None = None  # could be used for a "reset"?
    last_value: TProp | None = None  # the last value we saw from the device
    limits: tuple[int | float, int | float] | None = None
    sequence_max_length: int = 0
    description: str | None = None

    allowed_values: Sequence[TProp] | None = None
    is_read_only: bool = False
    is_pre_init: bool = False

    def __post_init__(self) -> None:
        """Ensure sound property configuration."""
        if self.allowed_values and self.limits:
            raise ValueError(
                f"Property {self.name!r} cannot have both allowed values and limits. "
                "Please choose one or the other."
            )

    def __setattr__(self, name: str, value: Any) -> None:
        """Perform additional checks when setting attributes."""
        super().__setattr__(name, value)

        # setting allowed values also removes the limits
        if name == "allowed_values" and value is not None:
            self.limits = None


class PropertyController(Generic[TDev, TProp]):
    """Controls the state of a property connected to a device."""

    def __init__(
        self,
        property: PropertyInfo[TProp],
        fget: Callable[[TDev], TProp],  # there must be a getter
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
    def __get__(self, instance: TDev, owner: type[TDev]) -> TProp:
        """Update the property value by calling the getter on the Device instance."""
        if instance is None:
            return self
        val = self.fget(instance)  # cache the value
        object.__setattr__(self.property, "last_value", val)
        return val

    # same as "Property::Apply" in CMMCore
    def __set__(self, instance: TDev, value: TProp) -> None:
        """Update the property value by calling the setter on the Device instance."""
        if self.fset is None:
            raise AttributeError("can't set attribute")
        if self.property.allowed_values and value not in self.property.allowed_values:
            raise ValueError(
                f"Value '{value}' is not allowed for property '{self.property.name}'. "
                f"Allowed values: {list(self.property.allowed_values)}."
            )
        if self.property.limits:
            try:
                value = float(value)  # type: ignore
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"Non-numeric value {value!r} cannot be compared to the limits "
                    f"of property {self.property.name!r}: {self.property.limits}."
                ) from e
            min_, max_ = self.property.limits
            if not min_ <= cast(float, value) <= max_:
                raise ValueError(
                    f"Value {value!r} is not within the allowed range of property "
                    f"{self.property.name!r}: {self.property.limits}."
                )
        self.fset(instance, value)

    def setter(self, fset: Callable[[TDev, TProp], None]) -> Self:
        """Decorate a method to set the property on the device."""
        self.fset = fset
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
    is_read_only: bool = ...,
    is_pre_init: bool = ...,
) -> Callable[[Callable[[TDev], TProp]], PropertyController[TDev, TProp]]: ...
@overload  # when used with keyword arguments including limits
def pymm_property(
    *,
    limits: tuple[TLim, TLim] | None,  # cannot be combined with allowed_values
    sequence_max_length: int = ...,
    is_read_only: bool = ...,
    is_pre_init: bool = ...,
) -> Callable[[Callable[[TDev], TLim]], PropertyController[TDev, TLim]]: ...
@overload  # when used with keyword arguments without allowed_values or limits
def pymm_property(
    *,
    sequence_max_length: int = ...,
    is_read_only: bool = ...,
    is_pre_init: bool = ...,
) -> Callable[[Callable[[TDev], TLim]], PropertyController[TDev, TLim]]: ...
def pymm_property(
    fget: Callable[[TDev], TProp] | None = None,
    *,
    limits: tuple[TLim, TLim] | None = None,
    sequence_max_length: int = 0,
    allowed_values: Sequence[TProp] | None = None,
    is_read_only: bool = False,
    is_pre_init: bool = False,
) -> (
    PropertyController[TDev, TProp]
    | Callable[[Callable[[TDev], TProp]], PropertyController[TDev, TProp]]
):
    """Decorate a pymmcore property method."""

    def _inner(fget: Callable[[TDev], TProp]) -> PropertyController[TDev, TProp]:
        prop = PropertyInfo(
            name=fget.__name__,
            description=fget.__doc__,
            limits=limits,
            sequence_max_length=sequence_max_length,
            allowed_values=allowed_values,
            is_read_only=is_read_only,
            is_pre_init=is_pre_init,
        )

        return PropertyController(property=prop, fget=fget)

    return _inner if fget is None else _inner(fget)
