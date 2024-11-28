from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Sequence

    pass

PropType = TypeVar("PropType")


# probably not...  could scrap the pattern all together, or use psygnal.Signal
# on the Property object
class PropertyAction:
    """Represents an action to be executed on property access or update."""

    def __init__(
        self,
        before_get: Callable[[Property], Any] | None = None,
        after_set: Callable[[Property], Any] | None = None,
    ):
        self.before_get = before_get
        self.after_set = after_set

    def execute_before_get(self, prop: Property) -> None:
        if self.before_get:
            self.before_get(prop)

    def execute_after_set(self, prop: Property) -> None:
        if self.after_set:
            self.after_set(prop)


@dataclass
class Property(Generic[PropType]):
    name: str
    value: PropType
    read_only: bool = False
    allowed_values: Sequence[PropType] | None = None
    limits: tuple[float, float] | None = None
    action: PropertyAction | None = None
    sequence_max_length: int = 0

    @property
    def is_sequenceable(self) -> bool:
        return self.sequence_max_length > 0

    def get(self) -> PropType:
        if self.action:
            self.action.execute_before_get(self)
        return self.value

    def set(self, new_value: PropType) -> None:
        if self.read_only:
            raise ValueError(f"Property '{self.name}' is read-only.")
        if self.allowed_values and new_value not in self.allowed_values:
            raise ValueError(
                f"Value '{new_value}' is not allowed for property '{self.name}'. "
                f"Allowed values: {list(self.allowed_values)}."
            )
        if self.limits:
            min_, max_ = self.limits
            # FIXME: this comparison will break if for some reason limits has been set
            # but the new_value is not a float.  Determine most correct fix.
            if not (min_ <= new_value <= max_):  # type: ignore
                raise ValueError(
                    f"Value '{new_value}' is outside limits {self.limits}."
                )
        self.value = new_value
        if self.action:
            self.action.execute_after_set(self)
