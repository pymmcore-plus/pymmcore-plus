from abc import abstractmethod
from typing import ClassVar, Literal

from pymmcore_plus.core import DeviceType
from pymmcore_plus.core._constants import FocusDirection

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


class StageDevice(_BaseStage[float]):
    """ABC for Stage devices."""

    _TYPE: ClassVar[Literal[DeviceType.Stage]] = DeviceType.Stage

    @abstractmethod
    def set_position_um(self, val: float) -> None:
        """Set the position of the stage in microns."""

    @abstractmethod
    def get_position_um(self) -> float:
        """Returns the current position of the stage in microns."""

    @abstractmethod
    def set_origin(self) -> None:
        """Zero the stage's coordinates at the current position."""

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

    # -- Bridge protocol defaults --

    def set_position_steps(self, steps: int) -> None:
        """Default: 1:1 um-to-step mapping."""
        self.set_position_um(float(steps))

    def get_position_steps(self) -> int:
        """Default: 1:1 um-to-step mapping."""
        return int(self.get_position_um())

    def get_limits(self) -> tuple[float, float]:
        """Return stage travel limits (lower, upper). Override for real limits."""
        return (0.0, 0.0)

    def move(self, velocity: float) -> None:
        """Move at the given velocity. Override for motorized stages."""

    def is_stage_sequenceable(self) -> bool:
        """Return True if the stage supports triggered sequences."""
        return self.is_sequenceable()

    def get_stage_sequence_max_length(self) -> int:
        """Return maximum stage sequence length."""
        return self.get_sequence_max_length()

    def load_stage_sequence(self, positions: list[float]) -> None:
        """Load a stage position sequence."""
        self.send_sequence(tuple(positions))

    def start_stage_sequence(self) -> None:
        """Start the loaded stage sequence."""
        self.start_sequence()

    def stop_stage_sequence(self) -> None:
        """Stop the running stage sequence."""
        self.stop_sequence()


class _BaseXYStage(_BaseStage[tuple[float, float]]):
    """Shared logic for XYStage and XYStepperStage devices."""

    _TYPE: ClassVar[Literal[DeviceType.XYStage]] = DeviceType.XYStage

    def get_limits_um(self) -> tuple[float, float, float, float]:
        """Return (xMin, xMax, yMin, yMax). Override for real limits."""
        return (0.0, 0.0, 0.0, 0.0)

    def get_step_limits(self) -> tuple[int, int, int, int]:
        """Return (xMin, xMax, yMin, yMax) in steps. Override for real limits."""
        return (0, 0, 0, 0)

    def move(self, vx: float, vy: float) -> None:
        """Move at velocity. Override for motorized stages."""

    def is_xy_stage_sequenceable(self) -> bool:
        """Return True if the XY stage supports triggered sequences."""
        return self.is_sequenceable()

    def get_xy_stage_sequence_max_length(self) -> int:
        """Return maximum XY stage sequence length."""
        return self.get_sequence_max_length()

    def load_xy_stage_sequence(self, positions: list[tuple[float, float]]) -> None:
        """Load an XY stage position sequence."""
        self.send_sequence(tuple(positions))

    def start_xy_stage_sequence(self) -> None:
        """Start the loaded XY stage sequence."""
        self.start_sequence()

    def stop_xy_stage_sequence(self) -> None:
        """Stop the running XY stage sequence."""
        self.stop_sequence()


class XYStageDevice(_BaseXYStage):
    """ABC for XYStage devices that work in microns."""

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

    def set_origin(self) -> None:
        """Zero the stage's coordinates at the current position.

        This is a convenience method that calls `set_origin_x` and `set_origin_y`.
        Can be overridden for more efficient implementations.
        """
        self.set_origin_x()
        self.set_origin_y()

    def set_x_origin(self) -> None:
        """Zero the X axis. Alias for set_origin_x."""
        self.set_origin_x()

    def set_y_origin(self) -> None:
        """Zero the Y axis. Alias for set_origin_y."""
        self.set_origin_y()

    # -- Bridge protocol defaults --

    def set_position_steps(self, x: int, y: int) -> None:
        """Default: 1:1 um-to-step mapping."""
        self.set_position_um(float(x), float(y))

    def get_position_steps(self) -> tuple[int, int]:
        """Default: 1:1 um-to-step mapping."""
        ux, uy = self.get_position_um()
        return (int(ux), int(uy))

    def get_step_size_x_um(self) -> float:
        """Default step size. Override for real hardware."""
        return 1.0

    def get_step_size_y_um(self) -> float:
        """Default step size. Override for real hardware."""
        return 1.0

    def set_relative_position_steps(self, dx: int, dy: int) -> None:
        """Default: convert steps to um."""
        self.set_relative_position_um(
            float(dx) * self.get_step_size_x_um(),
            float(dy) * self.get_step_size_y_um(),
        )


class XYStepperStageDevice(_BaseXYStage):
    """ABC for XYStage devices driven by stepper motors.

    Rather than working in microns, you provide `set_position_steps`,
    `get_position_steps`, `get_step_size_x_um`, and `get_step_size_y_um`. As with a
    C++ stepper stage adapter, the core converts between microns and steps, applying
    the `TransposeMirrorX`/`TransposeMirrorY` properties and the adapter origin
    (`setAdapterOriginXY`; `setOriginXY` zeroes it). Moves are reported to the core
    as XY stage position changes.
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

    def set_relative_position_steps(self, dx: int, dy: int) -> None:
        """Move the stage by a relative amount.

        Can be overridden for more efficient implementations.
        """
        x_steps, y_steps = self.get_position_steps()
        self.set_position_steps(x_steps + dx, y_steps + dy)
