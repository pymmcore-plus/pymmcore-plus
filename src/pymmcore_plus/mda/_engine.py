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

        self._z_start = 0  # used for one_shot autofocus
        self._current_pos = 0  # used for one_shot autofocus

    def setup_sequence(self, sequence: MDASequence) -> None:
        """Setup the hardware for the entire sequence.

        (currently, this does nothing but get the global `CMMCorePlus` singleton
        if one is not already provided).
        """
        from ..core import CMMCorePlus

        self._mmc = self._mmc or CMMCorePlus.instance()

        self._z_plan = list(sequence.z_plan)

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
            if event.properties:
                z_device, z_af_device, z_af, use_af = self._get_properties_values(
                    event.properties
                )
                channel_offset = event.channel.z_offset
                channel_do_stack = event.channel.do_stack

                # if z_plan
                if len(event.sequence.z_plan) > 1:
                    z_idx = event.index["z"]

                    if not use_af:
                        self._mmc.setZPosition(event.z_pos)

                    elif z_idx == 0:
                        # set autofocus position
                        self._mmc.setPosition(z_af_device, z_af)
                        self._mmc.fullFocus()

                        self._mmc.setPosition(z_device, 250)  # to test with demo cfg

                        # get current resulting z position using z focus device
                        # and add any channel offset
                        self._z_start = (
                            self._mmc.getPosition(z_device) + channel_offset
                            if channel_offset
                            else self._mmc.getPosition(z_device)
                        )

                        # add z_plan offset to current z position or use z_start
                        # if not channel_do_stack
                        self._current_pos = (
                            self._z_start + self._z_plan[0]
                            if channel_do_stack
                            else self._z_start
                        )
    
                        self._mmc.setPosition(z_device, self._current_pos)

                    else:
                        # if not first frame, just add zplan offset.
                        # if offset is 0, use z_start
                        self._current_pos = (
                            self._z_start
                            if self._z_plan[z_idx] == 0
                            else self._current_pos + self._z_plan[z_idx]
                        )
                        self._mmc.setPosition(z_device, self._current_pos)

                # if no z_plan
                elif len(event.sequence.z_plan) == 0:
                    if not use_af:
                        self._mmc.setZPosition(event.z_pos)

                    else:
                        # set autofocus position
                        self._mmc.setPosition(z_af_device, z_af)
                        self._mmc.fullFocus()

                        self._mmc.setPosition(z_device, 250)  # to test with demo cfg

                        # add any channel offset
                        if channel_offset:
                            self._mmc.setPosition(
                                z_device, self._mmc.getPosition(z_device) + channel_offset
                            )

                else:
                    self._mmc.setZPosition(event.z_pos)

            else:
                self._mmc.setZPosition(event.z_pos)

        print("curr:", self._mmc.getPosition())

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

    def _get_properties_values(
        self, properties: list[PropertyTuple]
    ) -> tuple[str | None, str | None, float | None, bool | None]:
        """Get the values of the properties that are used for one_shot autofocus."""
        z_device, z_af_device, z_af, use_af = None, None, None, None

        for prop in properties:
            if prop.device_name == "z_device" and prop.property_name == "device_name":
                z_device = prop.property_value
            elif (
                prop.device_name == "z_autofocus_device"
                and prop.property_name == "device_name"
            ):
                z_af_device = prop.property_value
            elif (
                prop.device_name == "z_autofocus_device"
                and prop.property_name == "position"
            ):
                z_af = prop.property_value
            elif (
                prop.device_name == "z_autofocus_device"
                and prop.property_name == "state"
            ):
                use_af = prop.property_value

        return z_device, z_af_device, z_af, use_af


class EventPayload(NamedTuple):
    image: np.ndarray
