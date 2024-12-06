from abc import abstractmethod
from typing import ClassVar, Literal

from pymmcore_plus.core._constants import DeviceType

from ._device import SeqT, SequenceableDevice

__all__ = ["_BaseStage"]


class _BaseStage(SequenceableDevice[SeqT]):
    """Shared logic for Stage and XYStage devices."""

    @abstractmethod
    def home(self) -> None:
        """Move the stage to its home position."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the stage."""


class StageDevice(_BaseStage[float]):
    """ABC for Stage devices."""

    _TYPE: ClassVar[Literal[DeviceType.Stage]] = DeviceType.Stage

    @abstractmethod
    def set_position(self, val: float) -> None:
        """Set the position of the stage in microns."""

    @abstractmethod
    def get_position(self) -> float:
        """Returns the current position of the stage in microns."""

    @abstractmethod
    def set_origin(self) -> None:
        """Zero the stage's coordinates at the current position."""
