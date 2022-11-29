from typing import Any, Sequence

from pymmcore_plus import CMMCorePlus
from pymmcore_plus._logger import logger
from useq import MDAEvent, MDASequence


class SequencedEvent:
    """Meta-event that contains a sequence of triggerable/sequenceable events."""

    def __init__(self, events: Sequence[MDAEvent]):
        self._frozen: bool = False
        self.events = events
        z_positions: list[float] = []
        x_positions: list[float] = []
        y_positions: list[float] = []
        exposures: list[float] = []
        channels: list[str] = []
        for event in events:
            if event.z_pos is not None:
                z_positions.append(event.z_pos)
            if event.x_pos is not None:
                x_positions.append(event.x_pos)
            if event.y_pos is not None:
                y_positions.append(event.y_pos)
            if event.exposure is not None:
                exposures.append(event.exposure)
            if event.channel is not None:
                channels.append(event.channel.config)
        self.has_z_sequence = len(set(z_positions)) > 1
        self.has_xy_sequence = len(set(x_positions)) > 1 and len(set(y_positions)) > 1
        self.has_exposure_sequence = len(set(exposures)) > 1
        self.has_channel_sequence = len(set(channels)) > 1
        self.z_positions = tuple(z_positions)
        self.x_positions = tuple(x_positions)
        self.y_positions = tuple(y_positions)
        self.exposures = tuple(exposures)
        self.channels = tuple(channels)
        self._frozen = True

    def __setattr__(self, __name: str, __value: Any) -> None:
        """Set attribute."""
        if self._frozen:
            raise AttributeError("Cannot modify frozen object")
        super().__setattr__(__name, __value)

    @property
    def channel_info(self) -> tuple[str, str] | None:
        """Return channel group & config, or None."""
        e0 = self.events[0]
        return (e0.channel.group, e0.channel.config) if e0.channel else None


def _prep_sequence_hardware(core: CMMCorePlus, seqevent: SequencedEvent):
    if seqevent.has_exposure_sequence:
        core.loadExposureSequence(core.getCameraDevice(), seqevent.exposures)
    if seqevent.has_xy_sequence:
        core.loadXYStageSequence(
            core.getXYStageDevice(), seqevent.x_positions, seqevent.y_positions
        )
    if seqevent.has_z_sequence:
        core.loadStageSequence(core.getFocusDevice(), seqevent.z_positions)
    if seqevent.has_channel_sequence and seqevent.channel_info:
        # double check this
        for dev, prop, value in core.getConfigData(*seqevent.channel_info):
            core.loadPropertySequence(dev, prop, value)


def _submit_event_iterator(core: CMMCorePlus, sequence: MDASequence):
    _burst: list[MDAEvent] = []

    for event in sequence:
        logger.debug(f"event: {event}")
        # run hooks: on_event(event) -> bool

        # processAcquisitionEvent
        if not _burst:
            _burst.append(event)
        elif core.canSequenceEvents(_burst[-1], event, len(_burst)):
            _burst.append(event)
        else:
            ...
