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
            z_device = event.z_device
            if event.z_is_autofocus:
                self._mmc.fullFocus()
                z_pos = self._mmc.getPosition(event.z_device if event.z_device else self._mmc.getFocusDevice())
                self._mmc.setPosition(z_device or self._mmc.getFocusDevice())
            else:
                self._mmc.setPosition(z_device or self._mmc.getFocusDevice())
        if event.channel is not None:
            self._mmc.setConfig(event.channel.group, event.channel.config)
        if event.exposure is not None:
            self._mmc.setExposure(event.exposure)

        self._mmc.waitForSystem()

        # if event.x_pos is not None or event.y_pos is not None:
        #     x = event.x_pos if event.x_pos is not None else self._mmc.getXPosition()
        #     y = event.y_pos if event.y_pos is not None else self._mmc.getYPosition()
        #     self._mmc.setXYPosition(x, y)
        # if event.z_pos is not None:
        #     self._mmc.setZPosition(event.z_pos)
        # if event.channel is not None:
        #     self._mmc.setConfig(event.channel.group, event.channel.config)
        # if event.exposure is not None:
        #     self._mmc.setExposure(event.exposure)

        # self._mmc.waitForSystem()
        MDASequence(
            channels=[{'config':'GFP', 'group':'Channel', 'exposure':100.01}],
            stage_positions=[{'x':-72816.1, 'y':36313.64, 'z':4388.90}],
            # stage_positions=[{'x':-72816.1, 'y':36313.64, 'z':173.35, 'z_device':'TIPFSOffset', 'z_is_autofocus':True, 'name':'Pos000', 'sequence':None}],
            )

    def exec_event(self, event: MDAEvent) -> Any:
        """Execute an individual event and return the image data."""
        # TODO: add non-aquisition event-specific logic here later
        self._mmc.snapImage()
        return EventPayload(image=self._mmc.getImage())


class EventPayload(NamedTuple):
    image: np.ndarray
