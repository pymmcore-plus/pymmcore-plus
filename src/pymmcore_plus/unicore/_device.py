from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from typing import Any, Self

    from pymmcore_plus.core import DeviceType


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

    @abstractmethod
    def type(self) -> DeviceType:
        """Return the type of the device."""


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
