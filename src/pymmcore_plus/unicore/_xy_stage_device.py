from abc import abstractmethod
from typing import ClassVar, Literal

from pymmcore_plus.core import DeviceType

from ._stage import _BaseStage


# TODO: consider if we can just subclass StageDevice instead of _BaseStage
class XYStageDevice(_BaseStage[tuple[float, float]]):
    """ABC for XYStage devices."""

    _TYPE: ClassVar[Literal[DeviceType.XYStage]] = DeviceType.XYStage

    # TODO:
    # we can probably extend this base class with better initial functionality
    # see CXYStageBase in mmCoreAndDevices

    @abstractmethod
    def set_position_um(self, x: float, y: float) -> None:
        """Set the position of the XY stage in microns."""

    @abstractmethod
    def get_position_um(self) -> tuple[float, float]:
        """Returns the current position of the XY stage in microns."""

    @abstractmethod
    def set_origin_x(self) -> None:
        """Zero the stage's X coordinates at the current position."""

    @abstractmethod
    def set_origin_y(self) -> None:
        """Zero the stage's Y coordinates at the current position."""

    def set_adapter_origin_um(self, x: float, y: float) -> None:
        """Alter the software coordinate translation between micrometers and steps.

        ... such that the current position becomes the given coordinates.
        """
        # I don't quite understand what this method is supposed to do yet.
        # i think we can provide a base implementation, so it won't be abstractmethod
        # but i don't know what to put here.
        raise NotImplementedError("This method is not implemented for this device.")

    def set_origin(self) -> None:
        """Zero the stage's coordinates at the current position.

        This is a convenience method that calls `set_origin_x` and `set_origin_y`.
        Can be overridden for more efficient implementations.
        """
        self.set_origin_x()
        self.set_origin_y()

    def set_relative_position_um(self, dx: float, dy: float) -> None:
        """Move the stage by a relative amount.

        Can be overridden for more efficient implementations.
        """
        x, y = self.get_position_um()
        self.set_position_um(x + dx, y + dy)
