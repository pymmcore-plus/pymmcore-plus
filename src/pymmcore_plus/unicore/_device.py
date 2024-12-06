from __future__ import annotations

import threading
import time
from abc import ABC
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, final

from pymmcore_plus.core import DeviceType

from ._properties import PropertyController, PropertyInfo

if TYPE_CHECKING:
    from collections.abc import KeysView, Sequence

    from typing_extensions import Any, Self


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
    _prop_controllers: ClassVar[dict[str, PropertyController]]

    def __init__(self) -> None:
        super().__init__()
        self._label: str = ""
        # False -> Not initialized
        # True -> Initialized successfully
        # Exception -> Initialization failed, contains the exception
        self._initialized: bool | BaseException = False

    def __init_subclass__(cls) -> None:
        """Initialize the property controllers."""
        cls._prop_controllers = {
            p.property.name: p
            for p in cls.__dict__.values()
            if isinstance(p, PropertyController)
        }
        return super().__init_subclass__()

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

    def library(self) -> str:
        """Return the name of the module that implements the device."""
        return self.__module__

    def name(self) -> str:
        """Return the name of the device."""
        return f"{self.__class__.__name__}"

    def description(self) -> str:
        """Return a description of the device."""
        return self.__doc__ or ""

    def busy(self) -> bool:
        """Return `True` if the device is busy."""
        return False

    def wait_for_device(self, timeout_ms: float) -> None:
        """Wait for the device to not be busy."""
        deadline = time.perf_counter() + timeout_ms / 1000
        polling_interval = 0.01

        while True:
            with self:
                if not self.busy():
                    return
            if time.perf_counter() > deadline:
                label = self.get_label()
                raise TimeoutError(
                    f"Wait for device {label!r} timed out after {timeout_ms} ms"
                )
            time.sleep(polling_interval)

    # PROPERTIES

    @classmethod
    def get_property_names(cls) -> KeysView[str]:
        """Return the names of the properties."""
        return cls._prop_controllers.keys()

    def property(self, prop_name: str) -> PropertyInfo:
        """Return the property controller for a property."""
        return self._prop_controllers[prop_name].property

    def get_property_value(self, prop_name: str) -> Any:
        """Return the value of a property."""
        # TODO: catch errors
        return self._prop_controllers[prop_name].__get__(self, self.__class__)

    def set_property_value(self, prop_name: str, value: Any) -> None:
        """Set the value of a property."""
        # TODO: catch errors
        self._prop_controllers[prop_name].__set__(self, value)

    def load_property_sequence(self, prop_name: str, sequence: Sequence[Any]) -> None:
        """Load a sequence into a property."""
        self._prop_controllers[prop_name].load_sequence(self, sequence)

    def start_property_sequence(self, prop_name: str) -> None:
        """Start a sequence of a property."""
        self._prop_controllers[prop_name].start_sequence(self)

    def stop_property_sequence(self, prop_name: str) -> None:
        """Stop a sequence of a property."""
        self._prop_controllers[prop_name].stop_sequence(self)

    def set_property_allowed_values(
        self, prop_name: str, allowed_values: Sequence[Any]
    ) -> None:
        """Set the allowed values of a property."""
        self._prop_controllers[prop_name].property.allowed_values = allowed_values

    def set_property_limits(
        self, prop_name: str, limits: tuple[float, float] | None
    ) -> None:
        """Set the limits of a property."""
        self._prop_controllers[prop_name].property.limits = limits

    def set_property_sequence_max_length(self, prop_name: str, max_length: int) -> None:
        """Set the sequence max length of a property."""
        self._prop_controllers[prop_name].property.sequence_max_length = max_length

    def is_property_sequenceable(self, prop_name: str) -> bool:
        """Return `True` if the property is sequenceable."""
        return self._prop_controllers[prop_name].is_sequenceable


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
