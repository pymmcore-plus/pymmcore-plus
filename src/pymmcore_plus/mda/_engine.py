from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

from useq import MDAEvent, MDASequence, NoZ

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

        self.z_start = 0  # used for one_shot autofocus

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
            z_device = event.z_device or self._mmc.getFocusDevice()
            # is one_shot focus (autofocus)
            if event.z_autofocus_device and event.z_autofocus:
                z = event.z_pos

                if 'z' not in event.index or event.index["z"] == 0:
                # use autofocus only on the first frame
                # if event.index["z"] == 0:
                    z_af = event.z_autofocus
                    z_af_device = event.z_autofocus_device
                    #set autofocus position
                    self._mmc.setPosition(z_af_device, z_af)
                    self._mmc.fullFocus()
                    self._mmc.setPosition(z_device, 250)
                    # get current resulting z position using z focus device
                    self.z_start = self._mmc.getPosition(z_device)
                    # add event.z_pos (offset) to current z position
                    self._mmc.setPosition(z_device, self.z_start + z)
                else:
                    # if not first frame, just add event.z_pos (offset)
                    # to current z position. if offset is 0, use z_start
                    z_pos = self.z_start if z == 0 else self._mmc.getPosition(z_device) + z
                    self._mmc.setPosition(z_device,z_pos)

            else:
                self._mmc.setPosition(z_device, event.z_pos)

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


class EventPayload(NamedTuple):
    image: np.ndarray
