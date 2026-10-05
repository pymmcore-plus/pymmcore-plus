from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

from pymmcore_plus.core._constants import DeviceType, Keyword

from ._device_base import Device

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from typing import ClassVar, Literal, Self


class StateDevice(Device):
    """State device API, e.g. filter wheel, objective turret, etc.

    A state device is a device that at any point in time is in a single state out of a
    list of possible states, like a filter wheel, an objective turret, etc.  The
    interface contains functions to get and set the state, to give states human readable
    labels, and functions to make it possible to treat the state device as a shutter.

    In terms of implementation, this base class presents the device's state as the
    "State" property. As with C++ state device adapters, position labels (and the
    "Label" property) are owned by the core: the labels given here are only the
    defaults, and are changed with `CMMCore.defineStateLabel()`.

    Parameters
    ----------
    state_labels: Mapping[int, str] | Iterable[tuple[int, str]]
        A mapping (or iterable of 2-tuples) of integer state indices to default string
        labels.
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

        self._default_labels: dict[int, str] = {p: str(lb) for p, lb in states.items()}
        self.register_standard_properties()

    def register_standard_properties(self) -> None:
        """Register the State property."""
        states = tuple(self._default_labels)
        cls = type(self)
        self.register_property(
            name=Keyword.State,
            default_value=states[0],
            allowed_values=states,
            getter=cls.get_state,
            setter=cls._set_state,
        )

    def notify_state_changed(self, state: int) -> None:
        """Notify the core that the device moved on its own (e.g. by hand).

        The core is notified of both the State and Label properties.
        """
        if self._notify_ is not None:
            self._notify_.on_state_changed(state)

    def get_number_of_positions(self) -> int:
        """Return the number of available positions."""
        return len(self._default_labels)

    # ------------------ private methods for internal use ------------------

    def _set_state(self, state: int) -> None:
        # State property setter. Like C++ CStateDeviceBase, a core-initiated move
        # needs no notification: CMMCore updates its own state cache.
        self.set_state(state)

    # -- Bridge protocol --

    def _post_bridge_initialize(self) -> None:
        """Register the default position labels with C++ CStateDeviceBase."""
        if self._notify_ is not None:
            for pos, label in self._default_labels.items():
                self._notify_.set_position_label(pos, label)
