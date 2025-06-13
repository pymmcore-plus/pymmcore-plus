from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, cast

from pymmcore_plus.core._constants import DeviceType, Keyword

from ._device_base import Device

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from typing import ClassVar, Literal

    from pymmcore import StateLabel
    from typing_extensions import Self


class StateDevice(Device):
    """State device API, e.g. filter wheel, objective turret, etc.

    A state device is a device that at any point in time is in a single state out of a
    list of possible states, like a filter wheel, an objective turret, etc.  The
    interface contains functions to get and set the state, to give states human readable
    labels, and functions to make it possible to treat the state device as a shutter.

    In terms of implementation, this base class provides the basic functionality by
    presenting state and label as properties, which it keeps in sync with the
    underlying device.

    Parameters
    ----------
    state_labels: Mapping[int, str] | Iterable[tuple[int, str]]
        A mapping (or iterable of 2-tuples) of integer state indices to string labels.
    """

    # Mandatory methods for state devices

    @abstractmethod
    def get_state(self) -> int:
        """Get the current state of the device (integer index)."""
        ...

    @abstractmethod
    def set_state(self, position: int) -> None:
        """Set the state of the device (integer index)."""
        ...

    # ------------------ The rest is base class implementation ------------------
    # (adaptors may override these methods if desired)

    _TYPE: ClassVar[Literal[DeviceType.State]] = DeviceType.State

    @classmethod
    def from_count(cls, count: int) -> Self:
        """Simplified constructor with just a number of states."""
        if count < 1:
            raise ValueError("State device must have at least one state.")
        return cls({i: f"State-{i}" for i in range(count)})

    def __init__(
        self, state_labels: Mapping[int, str] | Iterable[tuple[int, str]], /
    ) -> None:
        super().__init__()
        if not (states := dict(state_labels)):  # pragma: no cover
            raise ValueError("State device must have at least one state.")

        self._state_to_label: dict[int, StateLabel] = states  # type: ignore[assignment]
        # reverse mapping for O(1) lookup
        self._label_to_state: dict[str, int] = {lbl: p for p, lbl in states.items()}

        self.register_standard_properties()

    def register_standard_properties(self) -> None:
        """Inspect the class for standard properties and register them."""
        states, labels = zip(*self._state_to_label.items())
        cls = type(self)
        self.register_property(
            name=Keyword.State,
            default_value=states[0],
            allowed_values=states,
            getter=cls.get_state,
            setter=cls._set_state,
        )
        self.register_property(
            name=Keyword.Label.value,
            default_value=labels[0],
            allowed_values=labels,
            getter=cls._get_current_label,
            setter=cls._set_current_label,
        )

    def set_position_or_label(self, pos_or_label: int | str) -> None:
        """Set the position of the device by index or label."""
        if isinstance(pos_or_label, str):
            label = pos_or_label
            pos = self.get_position_for_label(pos_or_label)
        else:
            pos = int(pos_or_label)
            label = self._state_to_label.get(pos, "")
        if pos not in self._state_to_label:
            raise ValueError(
                f"Position {pos} is not a valid state. "
                f"Available states: {self._state_to_label.keys()}"
            )
        self.set_property_value(Keyword.State, pos)  # will trigger set_state
        self.set_property_value(Keyword.Label.value, label)

    def assign_label_to_position(self, pos: int, label: str) -> None:
        """Assign a User-defined label to a position."""
        if not isinstance(pos, int):
            raise TypeError(f"Position must be an integer, got {type(pos).__name__}.")

        # update internal state
        self._state_to_label[pos] = label = cast("StateLabel", str(label))
        self._label_to_state[label] = pos
        self._update_allowed_labels()

    def get_position_for_label(self, label: str) -> int:
        """Return the position corresponding to the provided label."""
        if label not in self._label_to_state:
            raise KeyError(
                f"Label not defined: {label!r}. "
                f"Available labels: {self._state_to_label.values()}"
            )
        return self._label_to_state[label]

    # ------------------ private methods for internal use ------------------

    def _update_allowed_labels(self) -> None:
        """Update the allowed values for the label property."""
        label_prop_info = self.get_property_info(Keyword.Label)
        label_prop_info.allowed_values = list(self._state_to_label.values())

    def _set_state(self, state: int) -> None:
        # internal method to set the state, called by the property setter
        # to keep the label and state property in sync
        self.set_state(state)  # call the device-specific method
        label = self._state_to_label.get(state, "")
        self.set_property_value(Keyword.Label, label)

    def _get_current_label(self) -> str:
        # internal method to get the current label, called by the property getter
        # to keep the label and state property in sync
        pos = self.get_property_value(Keyword.State)
        return self._state_to_label.get(pos, "")

    def _set_current_label(self, label: str) -> None:
        # internal method to set the label, called by the property setter
        # to keep the label and state property in sync
        pos = self._label_to_state.get(label)
        if pos != self.get_property_value(Keyword.State):
            self.set_property_value(Keyword.State, pos)  # will trigger set_state
