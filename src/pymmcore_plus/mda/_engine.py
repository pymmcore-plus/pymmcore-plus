from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

from useq import MDAEvent, MDASequence, NoZ, PropertyTuple

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

        self._correction = 0  # used for one_shot autofocus

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
        if event.x_pos is not None or event.y_pos is not None:
            x = event.x_pos if event.x_pos is not None else self._mmc.getXPosition()
            y = event.y_pos if event.y_pos is not None else self._mmc.getYPosition()
            self._mmc.setXYPosition(x, y)

        if event.z_pos is not None:
            
            # TODO: exclude when absolute z_plan
            if event.autofocus is not None:
                z_af_device, z_af_pos = event.autofocus

                if len(event.sequence.z_plan) > 1:
                    # if first frame of z stack, calculate the correction
                    if event.index["z"] == 0:
                        z_after_af = self._execute_autofocus(z_af_device, z_af_pos)
                        # the first z event is the top of the stack, to know that
                        # is the starting z position we need to subtract the first
                        # z offset from the relative z plan (self._z_plan[0])
                        first_pos = event.z_pos -  list(event.sequence.z_plan)[0]
                        # calculate the correction to apply to each z position
                        self._correction = z_after_af - first_pos

                    self._mmc.setZPosition(event.z_pos + self._correction)

                else:  # no z or len(z_plan) == 1
                    z_after_af = self._execute_autofocus(z_af_device, z_af_pos)
                    self._mmc.setZPosition(z_after_af)
            else:
                self._mmc.setZPosition(event.z_pos)

        if event.channel is not None:
            self._mmc.setConfig(event.channel.group, event.channel.config)
        if event.exposure is not None:
            self._mmc.setExposure(event.exposure)

        self._mmc.waitForSystem()

    def exec_event(self, event: MDAEvent) -> Any:
        """Execute an individual event and return the image data."""
        # TODO: add non-aquisition event-specific logic here later
        self._mmc.snapImage()
        return EventPayload(image=self._mmc.getImage())
    
    def _execute_autofocus(self, z_af_device_name, z_af_pos) -> float:
        """Perform the autofocus."""
        # TODO: maybe add a try/except where if the autofocus set position fails,
        # we can set first the last z stage known position and then run the 
        # fullfocus method again. 
        self._mmc.setPosition(z_af_device_name, z_af_pos)
        self._mmc.fullFocus()
        return self._mmc.getZPosition()


class EventPayload(NamedTuple):
    image: np.ndarray
