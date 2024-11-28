from __future__ import annotations

import threading
from abc import ABC
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    TypeVar,
    final,
    overload,
)

from pymmcore_plus.core import DeviceType

from ._properties import Property

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from typing_extensions import Any, Self

    from ._properties import PropType


class _Lockable:
    """Mixin to make an object lockable."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._lock = threading.Lock()

    def __enter__(self) -> Self:
        self._lock.acquire()
        return self

    def __exit__(self, *args: Any) -> None:
        self._lock.release()

    def lock(self, blocking: bool = True, timeout: float = -1) -> bool:
        return self._lock.acquire(blocking, timeout)

    def unlock(self) -> None:
        self._lock.release()

    def locked(self) -> bool:
        return self._lock.locked()


class Device(_Lockable, ABC):
    """ABC for all Devices."""

    _TYPE: ClassVar[DeviceType] = DeviceType.UnknownType

    def __init__(self) -> None:
        super().__init__()
        self._properties: dict[str, Property] = {}
        self._label: str = ""
        # False -> Not initialized
        # True -> Initialized successfully
        # Exception -> Initialization failed, contains the exception
        self._initialized: bool | BaseException = False

    @overload
    def register_property(self, prop: Property, /) -> Property: ...
    @overload
    def register_property(
        self,
        name: str,
        /,
        *,
        value: PropType | None = None,
        read_only: bool = False,
        allowed_values: Sequence[PropType] | None = None,
        limits: tuple[float, float] | None = None,
        sequence_max_length: int = 0,
    ) -> Property: ...
    @final  # may not be overridden
    def register_property(
        self,
        name_or_prop: str | Property,
        value: PropType | None = None,
        read_only: bool = False,
        allowed_values: Sequence[PropType] | None = None,
        limits: tuple[float, float] | None = None,
        sequence_max_length: int = 0,
    ) -> Property:
        """Register a property."""
        if isinstance(name_or_prop, str):
            prop = Property(
                name=name_or_prop,
                value=value,
                read_only=read_only,
                allowed_values=allowed_values,
                limits=limits,
                sequence_max_length=sequence_max_length,
            )
        elif not isinstance(name_or_prop, Property):
            raise TypeError("name_or_prop must be a string or Property instance.")
        prop.is_pre_init = self._initialized is False
        self._properties[prop.name] = prop
        return prop

    @final
    def get_property(self, name: str) -> Any:
        """Get the value of a property."""
        try:
            prop = self._properties[name]
        except KeyError:
            raise KeyError(f"Property '{name}' not found.") from None
        return prop.get()

    @final
    def properties(self) -> Mapping[str, Property]:
        """Return a dictionary of the device's properties."""
        return MappingProxyType(self._properties)

    def initialize(self) -> None:
        """Initialize the device."""

    @final  # may not be overridden
    def get_label(self) -> str:
        return self._label

    @final
    def set_label(self, value: str) -> None:
        # for use by the device manager, but the device may know it's own label.
        self._label = str(value)

    @final
    @classmethod
    def type(cls) -> DeviceType:
        """Return the type of the device."""
        return cls._TYPE

    def name(self) -> str:
        """Return the name of the device."""
        return f"{self.__class__.__name__}"

    def description(self) -> str:
        """Return a description of the device."""
        return ""


SeqT = TypeVar("SeqT")


class SequenceableDevice(Device, Generic[SeqT]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # Note, for this base implementation, the type of the value is SeqT, which is a
        # variable that depends on the device type.  For example, for a stage device,
        # SeqT would be a float, but for an XYStage device, SeqT would be a tuple[float,
        # float].  It is up to the final subclass to handle this correctly when they
        # send the sequence to the device... or to reimplement more methods on this
        # class if they need different behavior.
        self._sequence: list[SeqT] = []

    # TODO: do we need both of these?  can't we just use max_length?
    def is_sequenceable(self) -> bool:
        """Return `True` if the device is sequenceable. Default is `False`."""
        return self.get_sequence_max_length() > 0

    def get_sequence_max_length(self) -> int:
        """Return the sequence."""
        return 0

    def add_to_sequence(self, value: SeqT) -> None:
        """Add a value to the sequence."""
        self._sequence.append(value)

    def clear_sequence(self) -> None:
        """Remove all values from the sequence."""
        self._sequence.clear()

    def start_sequence(self) -> None:
        """Start the sequence."""

    def stop_sequence(self) -> None:
        """Stop the sequence."""

    def send_sequence(self) -> None:
        """Signal that we are done appending sequence values.

        So that the adapter can send the whole sequence to the device
        """
        if self._sequence:
            raise NotImplementedError(
                "Sequence has been accumulated but send_sequence is not implemented."
            )
