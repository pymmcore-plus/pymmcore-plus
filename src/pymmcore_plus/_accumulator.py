"""Accumulate `setX` calls to a device value or property."""

from __future__ import annotations

import abc
import sys
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypeVar

import psygnal

from pymmcore_plus.core._constants import DeviceType
from pymmcore_plus.core._mmcore_plus import CMMCorePlus

if TYPE_CHECKING:
    from typing_extensions import Self
T = TypeVar("T")
DT = TypeVar("DT", bound=DeviceType)


class AbstractChangeAccumulator(ABC, Generic[T]):
    """Abstract base class for accumulating a series of `setX` calls to a device.

    A `ChangeAccumulator`` is a class that accumulates a series of `setX` calls to a
    device, retaining an internal target value, and emitting a signal when the device
    has reached its target and is idle. It can be shared by multiple players (e.g.
    widgets, or other classes) that want to control the same device, and allows them all
    to issue relative/absolute moves, and be notified when the device is idle.

    A common use case is to accumulate setPosition calls made to a stage device, where
    you might want to accumulate a series of relative moves, and snap an image only when
    the stage is idle after reaching its target position.
    """

    finished = psygnal.Signal()
    """Signal emitted when the device has reached its target and is idle."""

    def __init__(self, zero: T) -> None:
        self._zero = zero
        self._reset()

    def _reset(self) -> None:
        self._base: T | None = None
        self._delta: T | None = None

    # ------------------------ Public API ------------------------

    def add_relative(self, delta: T) -> None:
        """Add a relative value to the target."""
        if self._delta is None:
            self._base = self._get_value()
            self._delta = delta
        else:
            self._delta = self._add(self._delta, delta)
        self._issue_move()

    def set_absolute(self, target: T) -> None:
        """Assign an absolute value to the target.

        This will reset the accumulated state and issue a move to the target position.
        After the move finishes, new `move_relative()` calls are interpreted
        relative to *target*.
        """
        self._base = target  # anchor for later relatives
        self._delta = self._zero  # target == base + delta
        self._issue_move()

    def poll_done(self) -> bool:
        """Check if the device is done moving.

        This should be called repeatedly by some event loop driver.

        Returns True exactly once when:
        1. The device is idle (not busy) AND
        2. The last issued move command has been completed

        After returning True it resets its state and will return False until the next
        move_relative() call.
        """
        # if we have no base or delta, we're not moving
        if self._delta is None:
            return False

        # if the device is busy, we're not done
        if self._is_busy():
            return False

        # no new work, we're done
        self._reset()
        self.finished.emit()
        return True

    @property
    def is_moving(self) -> bool:
        """Returns True if the device is moving."""
        return self._delta is not None

    @property
    def target(self) -> T | None:
        """The target position of the stage. Or None if not moving."""
        if self._base is None or self._delta is None:
            return None
        return self._add(self._base, self._delta)

    # ------------------------ Public API ------------------------

    def _issue_move(self) -> None:
        # self._base and self._delta are guaranteed to be not None here
        target = self._add(self._base, self._delta)  # type: ignore[arg-type]
        # issue the move command
        try:
            self._set_value(target)
        except Exception:  # pragma: no cover
            from pymmcore_plus._logger import logger

            logger.exception(f"Error setting {type(self)} to {target}")

    # ------------------------ Abstract methods ------------------------

    @abstractmethod
    def _get_value(self) -> T:
        """Get the current position of the device."""

    @abstractmethod
    def _set_value(self, value: T) -> None:
        """Set the position of the device."""

    @abstractmethod
    def _add(self, a: T, b: T) -> T:
        """Add two values together.

        Provided for more complex types like sequences.
        """

    @abstractmethod
    def _is_busy(self) -> bool:
        """Return True if the device is busy."""


class FloatChangeAccumulator(AbstractChangeAccumulator[float]):
    def __init__(self) -> None:
        super().__init__(zero=0.0)

    def _add(self, a: float, b: float) -> float:
        return a + b


ZIP_STRICT = {"strict": True} if sys.version_info >= (3, 10) else {}


class SequenceChangeAccumulator(AbstractChangeAccumulator[Sequence[float]]):
    def __init__(self, sequence_length: int) -> None:
        self.sequence_length = sequence_length
        super().__init__(zero=[0.0] * sequence_length)

    def _add(self, a: Sequence[float], b: Sequence[float]) -> Sequence[float]:
        return [x + y for x, y in zip(a, b, **ZIP_STRICT)]


class DeviceAccumulator(abc.ABC, Generic[DT]):
    def __init__(
        self,
        *,
        device_label: str,
        mmcore: CMMCorePlus | None = None,
        **kwargs: Any,
    ) -> None:
        self._mmcore = mmcore or CMMCorePlus.instance()
        dev_type = self._device_type()
        if not self._mmcore.getDeviceType(device_label) == dev_type:  # pragma: no cover
            raise ValueError(
                f"Cannot create {self.__class__.__name__}. "
                f"Device {device_label!r} is not a {dev_type.name}. "
            )

        self._device_label = device_label
        super().__init__(**kwargs)

    def _is_busy(self) -> bool:
        return self._mmcore.deviceBusy(self._device_label)

    @classmethod
    @abstractmethod
    def _device_type(cls) -> DT:
        """Return the device type for this class."""

    _CACHE: ClassVar[dict[tuple[int, str], DeviceAccumulator]] = {}

    @classmethod
    def get_cached(cls, device: str, mmcore: CMMCorePlus | None = None) -> Self:
        """Get a cached instance of the class for the given (device, core) pair.

        This is intended to be called on the subclass for the device type you want to
        create. For example, if you want to create a `PositionChangeAccumulator` for a
        `StageDevice`, you would call: `PositionChangeAccumulator.get_cached(device)`.

        But it may also be called on the base class, in which case it will still return
        the correct subclass instance, but you will not have type safety on the return
        type.
        """
        mmcore = mmcore or CMMCorePlus.instance()
        cache_key = (id(mmcore), device)
        device_type = mmcore.getDeviceType(device)
        if cache_key not in DeviceAccumulator._CACHE:
            if device_type == cls._device_type():
                cls._CACHE[cache_key] = cls(device_label=device, mmcore=mmcore)
            else:
                for sub in cls.__subclasses__():
                    if sub._device_type() == device_type:  # noqa: SLF001
                        cls._CACHE[cache_key] = sub(device_label=device, mmcore=mmcore)
                        break
                else:
                    raise ValueError(
                        "No matching DeviceTypeMixin subclass found for device type "
                        f"{device_type.name} (for device {device!r})."
                    )
        obj = cls._CACHE[cache_key]
        if not isinstance(obj, cls):
            raise TypeError(
                f"Cannot create {cls.__name__} for {device!r}. "
                f"Device is a {device_type!r}, not a {cls._device_type().name}. "
            )
        return obj


class PositionChangeAccumulator(DeviceAccumulator, FloatChangeAccumulator):
    """Accumulator for single axis stage devices."""

    def __init__(self, device_label: str, mmcore: CMMCorePlus | None = None) -> None:
        super().__init__(device_label=device_label, mmcore=mmcore)

    @classmethod
    def _device_type(cls) -> Literal[DeviceType.StageDevice]:
        return DeviceType.StageDevice

    def _get_value(self) -> float:
        return self._mmcore.getPosition(self._device_label)

    def _set_value(self, value: float) -> None:
        self._mmcore.setPosition(self._device_label, value)


class XYPositionChangeAccumulator(DeviceAccumulator, SequenceChangeAccumulator):
    """Accumulator for XY stage devices."""

    def __init__(self, device_label: str, mmcore: CMMCorePlus | None = None) -> None:
        super().__init__(device_label=device_label, mmcore=mmcore, sequence_length=2)

    @classmethod
    def _device_type(cls) -> Literal[DeviceType.XYStageDevice]:
        return DeviceType.XYStageDevice

    def _get_value(self) -> Sequence[float]:
        return self._mmcore.getXYPosition(self._device_label)

    def _set_value(self, value: Sequence[float]) -> None:
        self._mmcore.setXYPosition(self._device_label, *value)
