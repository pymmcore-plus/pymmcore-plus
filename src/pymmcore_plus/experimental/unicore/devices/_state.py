from collections.abc import Iterable, Mapping
from typing import ClassVar, Literal, overload

from pymmcore_plus.core._constants import DeviceType, Keyword
from pymmcore_plus.experimental.unicore.devices._properties import pymm_property

from ._device import Device


class StateDevice(Device):
    """State device API, e.g. filter wheel, objective turret, etc.

    A state device is a device that at any point in time is in a single state out of a
    list of possible states, like a filter wheel, an objective turret, etc.  The
    interface contains functions to get and set the state, to give states human readable
    labels, and functions to make it possible to treat the state device as a shutter.

    Parameters
    ----------
    arg0 : int | Mapping[int, str] | Iterable[tuple[int, str]], optional
        If an integer, the number of states to create, by default 0.
        If a mapping or iterable of tuples, a map of state indices to labels.
    """

    _TYPE: ClassVar[Literal[DeviceType.State]] = DeviceType.State
    _states: dict[int, str]

    @overload
    def __init__(self, num_positions: int = ..., /) -> None: ...
    @overload
    def __init__(
        self, state_labels: Mapping[int, str] | Iterable[tuple[int, str]], /
    ) -> None: ...
    def __init__(
        self, arg0: int | Mapping[int, str] | Iterable[tuple[int, str]] = 0, /
    ) -> None:
        super().__init__()
        if isinstance(arg0, int):
            self._states = {i: f"State {i}" for i in range(arg0)}
        elif arg0 is not None:
            self._states = dict(arg0)
        else:
            self._states = {}

        if not self._states:
            raise ValueError("State device must have at least one state.")

    def initialize(self) -> None:
        states, labels = zip(*self._states.items())
        self.register_property(
            name=Keyword.State,
            default_value=states[0],
            getter=type(self).get_current_position,
            setter=type(self).set_position,
            # sequence_max_length=...,
            allowed_values=list(self._states.keys()),
        )
        self.register_property(
            name=Keyword.Label,
            default_value=labels[0],
            getter=type(self).get_current_label,
            setter=type(self).set_position,
            # sequence_max_length=...,
            allowed_values=list(self._states.values()),
        )

    @pymm_property(name=Keyword.Label)
    def label(self) -> str:
        """Return the label of the current position."""
        raise NotImplementedError

    def set_position(self, pos: int | str) -> None:
        """Set the position of the device.

        If `pos` is an integer, it is the index of the state to set.
        If `pos` is a string, it is the label of the state to set.
        """
        raise NotImplementedError

    def get_current_position(self) -> int:
        """Return the current position of the device."""
        raise NotImplementedError

    def get_current_label(self) -> str:
        """Return the label of the current position."""
        raise NotImplementedError

    def get_label_for_position(self, pos: int) -> str:
        """Returns the label of the provided position."""
        raise NotImplementedError

    def get_position_for_label(self, label: str) -> int:
        """Returns the position of the provided label."""
        raise NotImplementedError

    def get_number_of_positions(self) -> int:
        """Return the number of positions."""
        raise NotImplementedError

    # these methods are implemented in the C++ layer... but i think they're only there
    # for the StateDeviceShutter utility?
    #   virtual int SetGateOpen(bool open = true) = 0;
    #   virtual int GetGateOpen(bool& open) = 0;
