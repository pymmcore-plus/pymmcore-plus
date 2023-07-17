from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Iterable, Iterator, NamedTuple

from useq import MDAEvent, MDASequence

from ..core._sequencing import SequencedEvent
from ._protocol import PMDAEngine

if TYPE_CHECKING:
    import numpy as np

    from ..core import CMMCorePlus


class MDAEngine(PMDAEngine[SequencedEvent]):
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

    def _setup_sequence(self, seq_event: SequencedEvent) -> None:
        core = self._mmc
        cam_device = self._mmc.getCameraDevice()
        if seq_event.is_exposure_sequenced:
            core.loadExposureSequence(cam_device, seq_event.exposure_sequence)
        if seq_event.is_xy_sequenced:
            stage = core.getXYStageDevice()
            core.loadXYStageSequence(stage, seq_event.x_sequence, seq_event.y_sequence)
        if seq_event.is_z_sequenced:
            zstage = core.getFocusDevice()
            core.loadStageSequence(zstage, seq_event.z_sequence)

        loaded_configs = []
        if seq_event.is_channel_sequenced and seq_event.channel_info:
            # double check this
            # do we need to recheck if property is sequencable?
            group, config = seq_event.channel_info
            for dev, prop, value in core.getConfigData(group, config):
                core.loadPropertySequence(dev, prop, value)
                loaded_configs.append((dev, prop))

        # TODO: SLM
        core.prepareSequenceAcquisition(cam_device)

        if seq_event.is_z_sequenced:
            core.startStageSequence(zstage)
        if seq_event.is_xy_sequenced:
            core.startXYStageSequence(stage)
        for dev, prop in loaded_configs:
            core.startPropertySequence(dev, prop)
        if seq_event.is_exposure_sequenced:
            core.startExposureSequence(cam_device)

    def _setup_single_event(self, event: MDAEvent) -> None:
        if event.x_pos is not None or event.y_pos is not None:
            x = event.x_pos if event.x_pos is not None else self._mmc.getXPosition()
            y = event.y_pos if event.y_pos is not None else self._mmc.getYPosition()
            self._mmc.setXYPosition(x, y)
        if event.z_pos is not None:
            self._mmc.setZPosition(event.z_pos)
        if event.channel is not None:
            self._mmc.setConfig(event.channel.group, event.channel.config)
        if event.exposure is not None:
            self._mmc.setExposure(event.exposure)

    def setup_event(self, event: MDAEvent | SequencedEvent) -> None:
        """Set the system hardware (XY, Z, channel, exposure) as defined in the event.

        Parameters
        ----------
        event : MDAEvent
            The event to use for the Hardware config
        """
        if isinstance(event, SequencedEvent):
            self._setup_sequence(event)
        else:
            self._setup_single_event(event)
        self._mmc.waitForSystem()

    def _exec_sequenced_event(self, event: SequencedEvent) -> None:
        # TODO: add support for multiple camera devices
        self._mmc.startSequenceAcquisition(
            len(event.events),
            0,  # intervalMS
            True,  # stopOnOverflow
        )
        while True:
            if self._mmc.isSequenceRunning():
                time.sleep(0.001)

    def exec_event(self, event: MDAEvent | SequencedEvent) -> Any:
        """Execute an individual event and return the image data."""
        # TODO: add non-aquisition event-specific logic here later
        if isinstance(event, SequencedEvent):
            self._exec_sequenced_event(event)
        else:
            self._mmc.snapImage()
        return EventPayload(image=self._mmc.getImage())

    def event_iterator(
        self, events: Iterable[MDAEvent]
    ) -> Iterator[MDAEvent | SequencedEvent]:
        """Event iterator that merges events for hardware sequencing if possible.

        This simply wraps `for event in events: ...` inside `MDARunner.run()`
        """
        seq: list[MDAEvent] = []
        for event in events:
            # if the sequence is empty or the current event can be sequenced with the
            # previous event, add it to the sequence
            if not seq or self._mmc.canSequenceEvents(seq[-1], event, len(seq))[0]:
                seq.append(event)
            else:
                # otherwise, yield a SequencedEvent if the sequence has accumulated
                # more than one event, otherwise yield the single event
                yield seq[0] if len(seq) == 1 else SequencedEvent.create(seq)
                seq.clear()
        # yield any remaining events
        if seq:
            yield seq[0] if len(seq) == 1 else SequencedEvent.create(seq)


class EventPayload(NamedTuple):
    image: np.ndarray
