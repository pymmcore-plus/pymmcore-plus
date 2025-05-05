"""Batch setX calls to a device."""

from __future__ import annotations

import abc
import sys
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, Generic, Literal, TypeVar

import psygnal
from typing_extensions import TypeAlias

from pymmcore_plus.core._constants import DeviceType
from pymmcore_plus.core._mmcore_plus import CMMCorePlus

T = TypeVar("T")
DT = TypeVar("DT", bound=DeviceType)


class AbstractValueBatcher(ABC, Generic[T]):
    """Abstract base class for batching a series of setX calls to a device.

    A ValueBatcher is a class that batches a series of setX calls to a device, retaining
    an internal target value, and emitting a signal when the device has reached its
    target and is idle. It can be shared by multiple players (e.g. widgets, or other
    classes) that want to control the same device, and allows them all to issue
    relative/absolute moves, and be notified when the device is idle.

    A common use case is to batch setPosition calls to a stage device, where you might
    want to accumulate a series of relative moves, and snap an image only when the stage
    is idle.
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
        """Add a relative value to the batch."""
        if self._delta is None:
            # start new batch
            self._base = self._get_value()
            self._delta = delta
        else:
            self._delta = self._add(self._delta, delta)
        self._issue_move()

    def set_absolute(self, target: T) -> None:
        """Assign an absolute target position to the batch.

        This will reset the batch state and issue a move to the target position.
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

            logger.exception(f"Error setting ValueBatcher to {target}")

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


class FloatValueBatcher(AbstractValueBatcher[float]):
    def __init__(self) -> None:
        super().__init__(zero=0.0)

    def _add(self, a: float, b: float) -> float:
        return a + b


ZIP_STRICT = {"strict": True} if sys.version_info >= (3, 10) else {}


class SequenceValueBatcher(AbstractValueBatcher[Sequence[float]]):
    def __init__(self, sequence_length: int) -> None:
        self.sequence_length = sequence_length
        super().__init__(zero=[0.0] * sequence_length)

    def _add(self, a: Sequence[float], b: Sequence[float]) -> Sequence[float]:
        return [x + y for x, y in zip(a, b, **ZIP_STRICT)]


class DeviceTypeMixin(abc.ABC, Generic[DT]):
    def __init__(
        self,
        device_type: DT,
        *,
        device: str,
        mmcore: CMMCorePlus | None = None,
        **kwargs: Any,
    ) -> None:
        self._mmcore = mmcore or CMMCorePlus.instance()
        if not self._mmcore.getDeviceType(device) == device_type:  # pragma: no cover
            raise ValueError(f"Device {device!r} is not a {device_type.name}.")

        self._device = device
        self._device_type = device_type
        super().__init__(**kwargs)

    def _is_busy(self) -> bool:
        return self._mmcore.deviceBusy(self._device)


class StageBatcher(DeviceTypeMixin[Literal[DeviceType.StageDevice]], FloatValueBatcher):
    """Batcher for single axis stage devices."""

    def __init__(self, device: str, mmcore: CMMCorePlus | None = None) -> None:
        super().__init__(DeviceType.StageDevice, device=device, mmcore=mmcore)

    def _get_value(self) -> float:
        return self._mmcore.getPosition(self._device)

    def _set_value(self, value: float) -> None:
        self._mmcore.setPosition(self._device, value)


class XYStageBatcher(
    DeviceTypeMixin[Literal[DeviceType.XYStageDevice]], SequenceValueBatcher
):
    """Batcher for XY stage devices."""

    def __init__(self, device: str, mmcore: CMMCorePlus | None = None) -> None:
        super().__init__(
            DeviceType.XYStageDevice,
            device=device,
            mmcore=mmcore,
            sequence_length=2,
        )

    def _get_value(self) -> Sequence[float]:
        return self._mmcore.getXYPosition(self._device)

    def _set_value(self, value: Sequence[float]) -> None:
        self._mmcore.setXYPosition(self._device, *value)


DeviceBatcher: TypeAlias = "XYStageBatcher | StageBatcher"
_CACHED_BATCHERS: dict[tuple[int, str], DeviceBatcher] = {}


def get_device_batcher(
    device_label: str, mmcore: CMMCorePlus | None = None
) -> DeviceBatcher:
    """Get a value batcher for the given device.

    Stage devices are batched using a StageBatcher, and XYStage devices are batched
    using a XYStageBatcher.  Each controls the position of the device using methods
    `add_relative()` and `set_absolute()`, and emits a signal `finished` when the device
    is idle.

    Parameters
    ----------
    device_label : str
        The device label to get the batcher for.
    mmcore : CMMCorePlus, optional
        The CMMCorePlus instance to use. If not provided, the default instance is used.
    """
    mmcore = mmcore or CMMCorePlus.instance()

    cache_key = (id(mmcore), device_label)

    if cache_key not in _CACHED_BATCHERS:
        device_type = mmcore.getDeviceType(device_label)
        if device_type == DeviceType.XYStageDevice:
            _CACHED_BATCHERS[cache_key] = XYStageBatcher(device_label, mmcore)
        elif device_type == DeviceType.StageDevice:
            _CACHED_BATCHERS[cache_key] = StageBatcher(device_label, mmcore)
        else:  # pragma: no cover
            raise ValueError(
                f"Unsupported device type for value batching: {device_type.name}"
            )

        # pop the key on mmcore.events.systemConfigurationLoaded?
        # @mmcore.events.systemConfigurationLoaded.connect
        # def _on_system_configuration_loaded() -> None:
        #     # remove the batcher from the cache
        #     _CACHED_BATCHERS.pop(cache_key, None)

    return _CACHED_BATCHERS[cache_key]
