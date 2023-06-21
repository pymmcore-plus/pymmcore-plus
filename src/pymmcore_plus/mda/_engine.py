from __future__ import annotations
import contextlib

from typing import TYPE_CHECKING, Any, NamedTuple

from useq import MDAEvent, MDASequence

from pymmcore_plus._logger import logger

from ._protocol import PMDAEngine

if TYPE_CHECKING:
    import numpy as np

    from ..core import CMMCorePlus


class MDAEngine(PMDAEngine):
    """The default MDAengine that ships with pymmcore-plus.

    This implements the [`PMDAEngine`][pymmcore_plus.mda.PMDAEngine] protocol, and
    uses a [`CMMCorePlus`][pymmcore_plus.CMMCorePlus] instance to control the hardware.
    """

    def __init__(self, mmc: CMMCorePlus) -> None:
        self._mmc = mmc

        # used for one_shot autofocus to store the z correction for each position index
        self._z_correction: dict[int, float] = {}

    def setup_sequence(self, sequence: MDASequence) -> None:
        """Setup the hardware for the entire sequence.

        (currently, this does nothing but get the global `CMMCorePlus` singleton
        if one is not already provided).
        """
        from ..core import CMMCorePlus

        self._mmc = self._mmc or CMMCorePlus.instance()

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

            if event.autofocus is not None:
                # switch off autofocus device to let each position set it
                with contextlib.suppress(RuntimeError):
                    self._mmc.setProperty(self._mmc.getAutoFocusDevice(), "State", "Off")

                z_af_device, z_af_pos = event.autofocus

                z_plan = event.sequence.z_plan

                if len(z_plan) > 1 and not z_plan.is_relative:
                    self._mmc.setZPosition(event.z_pos)

                elif len(z_plan) > 1:
                    p_idx = event.index.get("p", 0)
                    # if first frame of z stack, calculate the correction
                    if event.index["z"] == 0:
                        # the first z event is the top or bottom of the stack,
                        # to know the starting z position we need to subtract the first
                        # z offset from the relative z plan (self._z_plan[0])
                        reference_position = event.z_pos - list(z_plan)[0]
                        # go to the reference position
                        self._mmc.setZPosition(
                                reference_position + self._z_correction[p_idx]
                            )
                        # run autofocus
                        z_after_af = self._execute_autofocus(z_af_device, z_af_pos)
                        # calculate the correction to apply to each z position
                        self._z_correction[p_idx] = z_after_af - reference_position

                    self._mmc.setZPosition(event.z_pos + self._z_correction[p_idx])
                    update_event = {"z_pos": event.z_pos + self._z_correction[p_idx]}

                else:  # no z or len(z_plan) == 1
                    z_after_af = self._execute_autofocus(z_af_device, z_af_pos)
                    self._mmc.setZPosition(z_after_af)
                    update_event = {"z_pos": z_after_af}

            else:
                self._mmc.setZPosition(event.z_pos)

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
    
    def _execute_autofocus(self, z_af_device_name, z_af_pos) -> float:
        """Perform the autofocus."""
        self._mmc.setPosition(z_af_device_name, z_af_pos)
        self._mmc.fullFocus()
        return self._mmc.getZPosition()


class EventPayload(NamedTuple):
    image: np.ndarray
