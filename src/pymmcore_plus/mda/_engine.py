from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, NamedTuple

from useq import HardwareAutofocus, MDAEvent, MDASequence, Snap  # type: ignore

from pymmcore_plus._logger import logger

from ._protocol import PMDAEngine

if TYPE_CHECKING:
    from ..core import CMMCorePlus

    class AutoFocusParams(NamedTuple):
        """Parameters for performing hardware autofocus.

        Attributes
        ----------
        autofocus_z_device_name : str
            Name of the hardware autofocus z device.
        af_motor_offset : float | None
            Before autofocus is performed, the autofocus motor should be moved to this
            offset.
        z_stage_position : float | None
            Before autofocus is performed, the z stage should be moved to this position.
            (Note: the Z-stage is the "main" z-axis, and is not the same as the
            autofocus device.)
        """

        autofocus_z_device_name: str
        af_motor_offset: float | None
        z_stage_position: float | None


class MDAEngine(PMDAEngine):
    """The default MDAengine that ships with pymmcore-plus.

    This implements the [`PMDAEngine`][pymmcore_plus.mda.PMDAEngine] protocol, and
    uses a [`CMMCorePlus`][pymmcore_plus.CMMCorePlus] instance to control the hardware.
    """

    def __init__(self, mmc: CMMCorePlus) -> None:
        self._mmc = mmc

        # used for one_shot autofocus to store the z correction for each position index.
        # map of {position_index: z_correction}
        self._z_correction: dict[int | None, float] = {}

    def setup_sequence(self, sequence: MDASequence) -> None:
        """Setup the hardware for the entire sequence.

        (currently, this does nothing but get the global `CMMCorePlus` singleton
        if one is not already provided).
        """
        from ..core import CMMCorePlus

        self._mmc = self._mmc or CMMCorePlus.instance()

        # switch off autofocus device if it is on
        self._mmc.enableContinuousFocus(False)

    def setup_event(self, event: MDAEvent) -> None:
        """Set the system hardware (XY, Z, channel, exposure) as defined in the event.

        Parameters
        ----------
        event : MDAEvent
            The event to use for the Hardware config
        """
        if event.x_pos is not None or event.y_pos is not None:
            x = event.x_pos if event.x_pos is not None else self._mmc.getXPosition()
            y = event.y_pos if event.y_pos is not None else self._mmc.getYPosition()
            self._mmc.setXYPosition(x, y)

        if event.z_pos is not None:
            p_idx = event.index.get("p", None)
            if p_idx not in self._z_correction:
                self._z_correction[p_idx] = 0.0
            self._mmc.setZPosition(event.z_pos + self._z_correction[p_idx])

        if event.channel is not None:
            self._mmc.setConfig(event.channel.group, event.channel.config)
        if event.exposure is not None:
            self._mmc.setExposure(event.exposure)

        self._mmc.waitForSystem()

    def exec_event(self, event: MDAEvent) -> Any:
        """Execute an individual event."""
        action = event.action if hasattr(event, "action") else Snap()

        # snap an image and emit the image data
        if action.type == "snap":
            self._mmc.snapImage()
            self._mmc.mda.events.frameReady.emit(self._mmc.getImage(), event)

        # execute hardware autofocus
        elif action.type == "hardware_autofocus" and event.z_pos is not None:
            # get position index
            p_idx = event.index.get("p", None)
            # run autofocus and get the new z position
            new_z = self._execute_autofocus(action)
            # get the correction to apply to each z position
            self._z_correction[p_idx] = event.z_pos - new_z

            logger.info(
                f"Autofocus event: z_correction: {self._z_correction[p_idx]}, "
                f"new_z_pos: {new_z})"
            )

        return None

    def _execute_autofocus(self, autofocus_event: HardwareAutofocus) -> float:
        """Perform the hardware autofocus.

        Returns the new z focus position.
        """
        self._mmc.setPosition(
            autofocus_event.autofocus_z_device_name,
            autofocus_event.autofocus_motor_offset,
        )
        self._mmc.waitForSystem()

        # perform fullFocus 3 times in case of failure
        try:
            self._mmc.fullFocus()
            self._mmc.waitForSystem()
        except RuntimeError:
            try:
                self._mmc.fullFocus()
                self._mmc.waitForSystem()
            except RuntimeError:
                try:
                    self._mmc.fullFocus()
                    self._mmc.waitForSystem()
                except RuntimeError:
                    warnings.warn("Hardware autofocus failed 3 times.", stacklevel=2)

        return self._mmc.getZPosition()
