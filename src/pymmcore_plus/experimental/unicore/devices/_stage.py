from abc import abstractmethod
from typing import ClassVar, Literal

from pymmcore_plus.core import DeviceType
from pymmcore_plus.core._constants import FocusDirection, Keyword

from ._device_base import SeqT, SequenceableDevice

__all__ = ["_BaseStage"]


class _BaseStage(SequenceableDevice[SeqT]):
    """Shared logic for Stage and XYStage devices."""

    @abstractmethod
    def home(self) -> None:
        """Move the stage to its home position."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the stage."""

    @abstractmethod
    def set_origin(self) -> None:
        """Zero the stage's coordinates at the current position."""


class StageDevice(_BaseStage[float]):
    """ABC for Stage devices."""

    _TYPE: ClassVar[Literal[DeviceType.Stage]] = DeviceType.Stage

    @abstractmethod
    def set_position_um(self, val: float) -> None:
        """Set the position of the stage in microns."""

    @abstractmethod
    def get_position_um(self) -> float:
        """Returns the current position of the stage in microns."""

    def get_focus_direction(self) -> FocusDirection:
        """Returns the focus direction of the stage."""
        return FocusDirection.Unknown

    def set_focus_direction(self, sign: int) -> None:
        """Sets the focus direction of the stage."""
        raise NotImplementedError(  # pragma: no cover
            "This device does not support setting focus direction"
        )

    def set_relative_position_um(self, d: float) -> None:
        """Move the stage by a relative amount.

        Can be overridden for more efficient implementations.
        """
        pos = self.get_position_um()
        self.set_position_um(pos + d)

    def set_adapter_origin_um(self, newZUm: float) -> None:
        """Enable software translation of coordinates.

        The current position of the stage becomes Z = newZUm.
        Only some stages support this functionality; it is recommended that
        set_origin() be used instead where available.
        """
        # Default implementation does nothing - subclasses can override
        pass

    def is_linear_sequenceable(self) -> bool:
        """Return True if the stage supports linear sequences.

        A linear sequence is defined by a step size and number of slices.
        """
        return False

    def set_linear_sequence(self, dZ_um: float, nSlices: int) -> None:
        """Load a linear sequence defined by step size and number of slices."""
        raise NotImplementedError(  # pragma: no cover
            "This device does not support linear sequences"
        )

    def is_continuous_focus_drive(self) -> bool:
        """Return True if positions can be set while continuous focus runs."""
        return False


# TODO: consider if we can just subclass StageDevice instead of _BaseStage
class XYStageDevice(_BaseStage[tuple[float, float]]):
    """ABC for XYStage devices."""

    _TYPE: ClassVar[Literal[DeviceType.XYStage]] = DeviceType.XYStage

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

    # ----------------------------------------------------------------

    def set_relative_position_um(self, dx: float, dy: float) -> None:
        """Move the stage by a relative amount.

        Can be overridden for more efficient implementations.
        """
        x, y = self.get_position_um()
        self.set_position_um(x + dx, y + dy)

    def set_adapter_origin_um(self, x: float, y: float) -> None:
        """Alter the software coordinate translation between micrometers and steps.

        ... such that the current position becomes the given coordinates.
        """
        # I don't quite understand what this method is supposed to do yet.
        # I believe it's here to give device adapter implementations a way to to set
        # the origin of some translation between micrometers and steps, rather than to
        # directly update the origin on the device itself.

    def set_origin(self) -> None:
        """Zero the stage's coordinates at the current position.

        This is a convenience method that calls `set_origin_x` and `set_origin_y`.
        Can be overridden for more efficient implementations.
        """
        self.set_origin_x()
        self.set_origin_y()


class XYStepperStageDevice(XYStageDevice):
    """ABC for XYStage devices that support stepper motors.

    In this variant, rather than providing `set_position_um` and `get_position_um`,
    you provide `set_position_steps`, `get_position_steps`, `get_step_size_x_um`,
    and `get_step_size_y_um`.  A default implementation of `set_position_um` and
    `get_position_um` is then provided that uses these methods, taking into account
    the XY-mirroring properties of the device.
    """

    @abstractmethod
    def set_position_steps(self, x: int, y: int) -> None:
        """Set the position of the XY stage in steps."""

    @abstractmethod
    def get_position_steps(self) -> tuple[int, int]:
        """Returns the current position of the XY stage in steps."""

    @abstractmethod
    def get_step_size_x_um(self) -> float:
        """Returns the step size of the X axis in microns."""

    @abstractmethod
    def get_step_size_y_um(self) -> float:
        """Returns the step size of the Y axis in microns."""

    # ----------------------------------------------------------------

    def __init__(self) -> None:
        super().__init__()
        self.register_property(name=Keyword.Transpose_MirrorX, default_value=False)
        self.register_property(name=Keyword.Transpose_MirrorY, default_value=False)
        self._origin_x_steps: int = 0
        self._origin_y_steps: int = 0

    def set_position_um(self, x: float, y: float) -> None:
        """Set the position of the XY stage in microns."""
        # Converts the given micrometer coordinates to steps and sets the position.
        mirror_x, mirror_y = self._get_orientation()

        steps_x = int(x / self.get_step_size_x_um())
        steps_y = int(y / self.get_step_size_y_um())

        if mirror_x:
            steps_x = -steps_x
        if mirror_y:
            steps_y = -steps_y

        x_steps = self._origin_x_steps + steps_x
        y_steps = self._origin_y_steps + steps_y
        self.set_position_steps(x_steps, y_steps)

        self.core.events.XYStagePositionChanged.emit(self.get_label(), x, y)

    def get_position_um(self) -> tuple[float, float]:
        """Get the position of the XY stage in microns."""
        # Converts the current steps to micrometer coordinates and returns the position.
        mirror_x, mirror_y = self._get_orientation()
        x_steps, y_steps = self.get_position_steps()

        x = (self._origin_x_steps - x_steps) * self.get_step_size_x_um()
        y = (self._origin_y_steps - y_steps) * self.get_step_size_y_um()
        if not mirror_x:
            x = -x
        if not mirror_y:
            y = -y

        return x, y

    def set_relative_position_steps(self, dx: int, dy: int) -> None:
        """Move the stage by a relative amount.

        Can be overridden for more efficient implementations.
        """
        x_steps, y_steps = self.get_position_steps()
        self.set_position_steps(x_steps + dx, y_steps + dy)

    def set_relative_position_um(self, dx: float, dy: float) -> None:
        """Default implementation for relative motion.

        Can be overridden for more efficient implementations.
        """
        mirror_x, mirror_y = self._get_orientation()

        if mirror_x:
            dx = -dx
        if mirror_y:
            dy = -dy

        steps_x = int(dx / self.get_step_size_x_um())
        steps_y = int(dy / self.get_step_size_y_um())

        self.set_relative_position_steps(steps_x, steps_y)

        x, y = self.get_position_um()
        self.core.events.XYStagePositionChanged.emit(self.get_label(), x, y)

    def set_adapter_origin_um(self, x: float = 0.0, y: float = 0.0) -> None:
        """Alter the software coordinate translation between micrometers and steps.

        ... such that the current position becomes the given coordinates.
        """
        mirror_x, mirror_y = self._get_orientation()
        x_steps, y_steps = self.get_position_steps()

        steps_x = int(x / self.get_step_size_x_um())
        steps_y = int(y / self.get_step_size_y_um())

        self._origin_x_steps = x_steps + (steps_x if mirror_x else -steps_x)
        self._origin_y_steps = y_steps + (steps_y if mirror_y else -steps_y)

    def set_origin(self) -> None:
        """Zero the stage's coordinates at the current position."""
        self.set_adapter_origin_um()

    def set_origin_x(self) -> None:
        """Zero the stage's X coordinates at the current position."""
        raise NotImplementedError  # pragma: no cover

    def set_origin_y(self) -> None:
        """Zero the stage's Y coordinates at the current position."""
        raise NotImplementedError  # pragma: no cover

    def _get_orientation(self) -> tuple[bool, bool]:
        return (
            self.get_property_value(Keyword.Transpose_MirrorX),
            self.get_property_value(Keyword.Transpose_MirrorY),
        )
