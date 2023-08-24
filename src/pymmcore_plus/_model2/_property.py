from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    TypeAlias,
)

from pymmcore_plus import CMMCorePlus, PropertyType

from ._core_link import CoreObject

if TYPE_CHECKING:
    PropVal: TypeAlias = bool | float | int | str
    PropGetter: TypeAlias = Callable[[CMMCorePlus, str, str], Any]
    PropSetter: TypeAlias = Callable[[CMMCorePlus, str, str, PropVal], None]


@dataclass
class Property:
    """Model of a device property."""

    device_name: str  # or device_label?
    name: str
    value: str = ""

    is_read_only: bool = False
    is_pre_init: bool = False
    allowed_values: tuple[str, ...] = field(default_factory=tuple)
    has_limits: bool = False
    lower_limit: float = 0.0
    upper_limit: float = 0.0
    property_type: PropertyType = PropertyType.Undef
    is_sequenceable: bool = False
    sequence_max_length: int = 0

    # def python_value(self) -> PropVal:
    #     """Return value cast to a Python type."""
    #     pytype = self.property_type.to_python()
    #     return pytype(self.value) if pytype is not None else self.value


VALUE = "value"
EXISTS = "exists"


class CoreProperty(Property, CoreObject):
    CORE_GETTERS: ClassVar[dict[str, PropGetter]] = {
        VALUE: CMMCorePlus.getProperty,
        "is_read_only": CMMCorePlus.isPropertyReadOnly,
        "is_pre_init": CMMCorePlus.isPropertyPreInit,
        "allowed_values": CMMCorePlus.getAllowedPropertyValues,
        "has_limits": CMMCorePlus.hasPropertyLimits,
        "lower_limit": CMMCorePlus.getPropertyLowerLimit,
        "upper_limit": CMMCorePlus.getPropertyUpperLimit,
        "property_type": CMMCorePlus.getPropertyType,
        "is_sequenceable": CMMCorePlus.isPropertySequenceable,
        "sequence_max_length": CMMCorePlus.getPropertySequenceMaxLength,
        EXISTS: CMMCorePlus.hasProperty,
    }
    CORE_SETTERS: ClassVar[dict[str, PropSetter]] = {
        "value": CMMCorePlus.setProperty,
    }

    def _core_args(self) -> tuple[str, str]:
        return self.device_name, self.name

    def follow_core(self, core: CMMCorePlus) -> None:
        core.events.propertyChanged.connect(self._on_core_change)

    def unfollow_core(self, core: CMMCorePlus) -> None:
        core.events.propertyChanged.disconnect(self._on_core_change)

    def _on_core_change(self, dev: str, prop: str, new_val: str) -> None:
        if dev == self.device_name and prop == self.name:
            self.value = new_val
