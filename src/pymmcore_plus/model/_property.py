from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Container, TypeAlias

from pymmcore_plus import CMMCorePlus, PropertyType

from ._core_link import CoreObject

if TYPE_CHECKING:
    from ._core_link import ErrCallback

    PropVal: TypeAlias = bool | float | int | str
    PropGetter: TypeAlias = Callable[[CMMCorePlus, str, str], Any]
    PropSetter: TypeAlias = Callable[[CMMCorePlus, str, str, PropVal], None]


@dataclass
class Property(CoreObject):
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

    CORE_GETTERS: ClassVar[dict[str, PropGetter]] = {
        "value": CMMCorePlus.getProperty,
        "is_read_only": CMMCorePlus.isPropertyReadOnly,
        "is_pre_init": CMMCorePlus.isPropertyPreInit,
        "allowed_values": CMMCorePlus.getAllowedPropertyValues,
        "has_limits": CMMCorePlus.hasPropertyLimits,
        "lower_limit": CMMCorePlus.getPropertyLowerLimit,
        "upper_limit": CMMCorePlus.getPropertyUpperLimit,
        "property_type": CMMCorePlus.getPropertyType,
        "is_sequenceable": CMMCorePlus.isPropertySequenceable,
        "sequence_max_length": CMMCorePlus.getPropertySequenceMaxLength,
        "exists": CMMCorePlus.hasProperty,
    }

    def _core_args(self) -> tuple[str, str]:
        # the first two args to all of the funcs in CORE_GETTERS
        return self.device_name, self.name

    def apply_to_core(
        self,
        core: CMMCorePlus,
        *,
        exclude: Container[str] = (),
        on_err: ErrCallback | None = None,
        then_update: bool = True,
    ) -> None:
        """Apply the property to the given Core instance."""
        # same as super().apply_to_core(core, *args, **kwargs)
        # but much simpler
        if "value" in exclude:
            return
        try:
            core.setProperty(self.device_name, self.name, self.value)
        except Exception as e:
            if callable(on_err):
                on_err(self, "value", e)
        if then_update:
            self.value = core.getProperty(self.device_name, self.name)

    # def follow_core(self, core: CMMCorePlus) -> None:
    #     core.events.propertyChanged.connect(self._on_core_change)

    # def unfollow_core(self, core: CMMCorePlus) -> None:
    #     core.events.propertyChanged.disconnect(self._on_core_change)

    # def _on_core_change(self, dev: str, prop: str, new_val: str) -> None:
    #     if dev == self.device_name and prop == self.name:
    #         self.value = new_val

    # def python_value(self) -> PropVal:
    #     """Return value cast to a Python type."""
    #     pytype = self.property_type.to_python()
    #     return pytype(self.value) if pytype is not None else self.value
