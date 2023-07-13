from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, NamedTuple, cast

from useq import MDAEvent, MDASequence

from pymmcore_plus._logger import logger

from ._protocol import PMDAEngine

if TYPE_CHECKING:
    import numpy as np

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
        self._z_correction: dict[str, float] = {}

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
        update_event = {}  # to update the event in case of any autofocus correction

        if event.x_pos is not None or event.y_pos is not None:
            x = event.x_pos if event.x_pos is not None else self._mmc.getXPosition()
            y = event.y_pos if event.y_pos is not None else self._mmc.getYPosition()
            self._mmc.setXYPosition(x, y)

        if event.z_pos is not None:
            # get position index if it exists else use 0
            p_idx = f"p{event.index.get('p', None)}"
            # run autofocus if specified in the event
            if event.autofocus is not None:  # type: ignore
                # get the correction to apply to each z position
                self._z_correction[p_idx] = self._execute_autofocus(event.autofocus)  # type: ignore  # noqa: E501
                # set updated z position with the correction
                self._mmc.setZPosition(event.z_pos + self._z_correction[p_idx])
                # update event to reflect the new z position
                update_event = {"z_pos": event.z_pos + self._z_correction[p_idx]}
            else:
                # if autofocus is not used in this event, just set the z position
                # + correction if any.
                p_idx = "p0" if p_idx is None else p_idx
                if p_idx not in self._z_correction:
                    self._z_correction[p_idx] = 0.0
                self._mmc.setZPosition(event.z_pos + self._z_correction[p_idx])
                # update event to reflect the new z position
                if self._z_correction[p_idx]:
                    update_event = {"z_pos": event.z_pos + self._z_correction[p_idx]}

        if event.channel is not None:
            self._mmc.setConfig(event.channel.group, event.channel.config)
        if event.exposure is not None:
            self._mmc.setExposure(event.exposure)

        if update_event:
            logger.info(f"Updated event: {event.copy(update=update_event)}")

        self._mmc.waitForSystem()

    def exec_event(self, event: MDAEvent) -> Any:
        """Execute an individual event and return the image data."""
        # TODO: add non-aquisition event-specific logic here later
        self._mmc.snapImage()
        return EventPayload(image=self._mmc.getImage())

    def _execute_autofocus(self, autofocus_event: AutoFocusParams) -> float:
        """Perform the autofocus.

        Returns the correction to be applied to the focus motor position.
        """
        self._mmc.setPosition(
            autofocus_event.autofocus_z_device_name,
            cast(float, autofocus_event.af_motor_offset),
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
                    return 0.0

        return self._mmc.getZPosition() - cast(float, autofocus_event.z_stage_position)


class EventPayload(NamedTuple):
    image: np.ndarray
