from __future__ import annotations

import time
from typing import TYPE_CHECKING, Iterable, Iterator, NamedTuple, Sequence, cast

from useq import HardwareAutofocus, MDAEvent, MDASequence

from pymmcore_plus._logger import logger
from pymmcore_plus._util import retry
from pymmcore_plus.core._sequencing import SequencedEvent

from ._protocol import PMDAEngine

if TYPE_CHECKING:
    import numpy as np

    from pymmcore_plus.core import CMMCorePlus


class MDAEngine(PMDAEngine):
    """The default MDAengine that ships with pymmcore-plus.

    This implements the [`PMDAEngine`][pymmcore_plus.mda.PMDAEngine] protocol, and
    uses a [`CMMCorePlus`][pymmcore_plus.CMMCorePlus] instance to control the hardware.

    Attributes
    ----------
    mmcore: CMMCorePlus
        The `CMMCorePlus` instance to use for hardware control.
    use_hardware_sequencing : bool
        Whether to use hardware sequencing if possible. If `True`, the engine will
        attempt to combine MDAEvents into a single `SequencedEvent` if
        [`core.canSequenceEvents()`][pymmcore_plus.CMMCorePlus.canSequenceEvents]
        reports that the events can be sequenced. This can be set after instantiation.
        By default, this is `False`, in order to avoid unexpected behavior, particularly
        in testing and demo scenarios.  But in many "real world" scenarios, this can be
        set to `True` to improve performance.
    """

    def __init__(self, mmc: CMMCorePlus, use_hardware_sequencing: bool = False) -> None:
        self._mmc = mmc
        self.use_hardware_sequencing = use_hardware_sequencing

        # used for one_shot autofocus to store the z correction for each position index.
        # map of {position_index: z_correction}
        self._z_correction: dict[int | None, float] = {}

        # This is used to determine whether we need to re-enable autoshutter after
        # the sequence is done (assuming a event.keep_shutter_open was requested)
        # Note: getAutoShutter() is True when no config is loaded at all
        self._autoshutter_was_set: bool = self._mmc.getAutoShutter()

    @property
    def mmcore(self) -> CMMCorePlus:
        """The `CMMCorePlus` instance to use for hardware control."""
        return self._mmc

    # ===================== Protocol Implementation =====================

    def setup_sequence(self, sequence: MDASequence) -> None:
        """Setup the hardware for the entire sequence.

        (currently, this does nothing but get the global `CMMCorePlus` singleton
        if one has not already been provided).
        """
        if not self._mmc:  # pragma: no cover
            from pymmcore_plus.core import CMMCorePlus

            self._mmc = CMMCorePlus.instance()

        if px_size := self._mmc.getPixelSizeUm():
            self._update_grid_fov_sizes(px_size, sequence)

        self._autoshutter_was_set = self._mmc.getAutoShutter()

    def _update_grid_fov_sizes(self, px_size: float, sequence: MDASequence) -> None:
        *_, x_size, y_size = self._mmc.getROI()
        fov_width = x_size * px_size
        fov_height = y_size * px_size

        if sequence.grid_plan:
            sequence.grid_plan.fov_width = fov_width
            sequence.grid_plan.fov_height = fov_height

        # set fov to any stage positions sequences
        for p in sequence.stage_positions:
            if p.sequence and p.sequence.grid_plan:
                p.sequence.grid_plan.fov_height = fov_height
                p.sequence.grid_plan.fov_width = fov_width

    def setup_event(self, event: MDAEvent) -> None:
        """Set the system hardware (XY, Z, channel, exposure) as defined in the event.

        Parameters
        ----------
        event : MDAEvent
            The event to use for the Hardware config
        """
        if isinstance(event, SequencedEvent):
            self.setup_sequenced_event(event)
        else:
            self.setup_single_event(event)
        self._mmc.waitForSystem()

    def exec_event(self, event: MDAEvent) -> EventPayload | None:
        """Execute an individual event and return the image data."""
        action = getattr(event, "action", None)
        if isinstance(action, HardwareAutofocus):
            # skip if no autofocus device is found
            if not self._mmc.getAutoFocusDevice():
                logger.warning("No autofocus device found. Cannot execute autofocus.")
                return None

            try:
                # execute hardware autofocus
                new_correction = self._execute_autofocus(action)
            except RuntimeError as e:
                logger.warning("Hardware autofocus failed. %s", e)
            else:
                # store correction for this position index
                p_idx = event.index.get("p", None)
                self._z_correction[p_idx] = new_correction
            return None

        if isinstance(event, SequencedEvent):
            return self.exec_sequenced_event(event)
        else:
            return self.exec_single_event(event)

    def event_iterator(self, events: Iterable[MDAEvent]) -> Iterator[MDAEvent]:
        """Event iterator that merges events for hardware sequencing if possible.

        This wraps `for event in events: ...` inside `MDARunner.run()` and combines
        sequenceable events into an instance of `SequencedEvent` if
        `self.use_hardware_sequencing` is `True`.
        """
        if not self.use_hardware_sequencing:
            yield from events
            return

        seq: list[MDAEvent] = []
        for event in events:
            # if the sequence is empty or the current event can be sequenced with the
            # previous event, add it to the sequence
            if not seq or self._mmc.canSequenceEvents(seq[-1], event, len(seq)):
                seq.append(event)
            else:
                # otherwise, yield a SequencedEvent if the sequence has accumulated
                # more than one event, otherwise yield the single event
                yield seq[0] if len(seq) == 1 else SequencedEvent.create(seq)
                # add this current event and start a new sequence
                seq = [event]
        # yield any remaining events
        if seq:
            yield seq[0] if len(seq) == 1 else SequencedEvent.create(seq)

    # ===================== Regular Events =====================

    def setup_single_event(self, event: MDAEvent) -> None:
        """Setup hardware for a single (non-sequenced) event.

        This method is not part of the PMDAEngine protocol (it is called by
        `setup_event`, which *is* part of the protocol), but it is made public
        in case a user wants to subclass this engine and override this method.
        """
        if event.keep_shutter_open:
            ...

        if event.x_pos is not None or event.y_pos is not None:
            self._set_event_position(event)
        if event.z_pos is not None:
            self._set_event_z(event)

        if event.channel is not None:
            try:
                self._mmc.setConfig(event.channel.group, event.channel.config)
            except Exception as e:
                logger.warning("Failed to set channel. %s", e)
        if event.exposure is not None:
            try:
                self._mmc.setExposure(event.exposure)
            except Exception as e:
                logger.warning("Failed to set exposure. %s", e)

        if (
            # (if autoshutter wasn't set at the beginning of the sequence
            # then it never matters...)
            self._autoshutter_was_set
            # if we want to leave the shutter open after this event, and autoshutter
            # is currently enabled...
            and event.keep_shutter_open
            and self._mmc.getAutoShutter()
        ):
            # we have to disable autoshutter and open the shutter
            self._mmc.setAutoShutter(False)
            self._mmc.setShutterOpen(True)

    def exec_single_event(self, event: MDAEvent) -> EventPayload | None:
        """Execute a single (non-triggered) event and return the image data.

        This method is not part of the PMDAEngine protocol (it is called by
        `exec_event`, which *is* part of the protocol), but it is made public
        in case a user wants to subclass this engine and override this method.
        """
        try:
            self._mmc.snapImage()
        except Exception as e:
            logger.warning("Failed to snap image. %s", e)
            return None
        if not event.keep_shutter_open:
            self._mmc.setShutterOpen(False)
        return EventPayload(image=self._mmc.getImage())

    def teardown_event(self, event: MDAEvent) -> None:
        """Teardown state of system (hardware, etc.) after `event`."""
        # autoshutter was set at the beginning of the sequence, and this event
        # doesn't want to leave the shutter open.  Re-enable autoshutter.
        if not event.keep_shutter_open and self._autoshutter_was_set:
            self._mmc.setAutoShutter(True)

    def teardown_sequence(self, sequence: MDASequence) -> None:
        """Perform any teardown required after the sequence has been executed."""
        pass

    # ===================== Sequenced Events =====================

    def setup_sequenced_event(self, event: SequencedEvent) -> None:
        """Setup hardware for a sequenced (triggered) event.

        This method is not part of the PMDAEngine protocol (it is called by
        `setup_event`, which *is* part of the protocol), but it is made public
        in case a user wants to subclass this engine and override this method.
        """
        core = self._mmc
        cam_device = self._mmc.getCameraDevice()

        if event.exposure_sequence:
            core.loadExposureSequence(cam_device, event.exposure_sequence)
        if event.x_sequence:  # y_sequence is implied and will be the same length
            stage = core.getXYStageDevice()
            core.loadXYStageSequence(stage, event.x_sequence, event.y_sequence)
        if event.z_sequence:
            zstage = core.getFocusDevice()
            core.loadStageSequence(zstage, event.z_sequence)
        if prop_seqs := event.property_sequences(core):
            for (dev, prop), value_sequence in prop_seqs.items():
                core.loadPropertySequence(dev, prop, value_sequence)

        # TODO: SLM
        core.prepareSequenceAcquisition(cam_device)

        # start sequences or set non-sequenced values
        if event.x_sequence:
            core.startXYStageSequence(stage)
        elif event.x_pos is not None or event.y_pos is not None:
            self._set_event_position(event)

        if event.z_sequence:
            core.startStageSequence(zstage)
        elif event.z_pos is not None:
            self._set_event_z(event)

        if event.exposure_sequence:
            core.startExposureSequence(cam_device)
        elif event.exposure is not None:
            core.setExposure(event.exposure)

        if prop_seqs:
            for dev, prop in prop_seqs:
                core.startPropertySequence(dev, prop)
        elif event.channel is not None:
            core.setConfig(event.channel.group, event.channel.config)

    def exec_sequenced_event(self, event: SequencedEvent) -> EventPayload:
        """Execute a sequenced (triggered) event and return the image data.

        This method is not part of the PMDAEngine protocol (it is called by
        `exec_event`, which *is* part of the protocol), but it is made public
        in case a user wants to subclass this engine and override this method.
        """
        # TODO: add support for multiple camera devices
        n_events = len(event.events)

        # Start sequence
        # Note that the overload of startSequenceAcquisition that takes a camera
        # label does NOT automatically initialize a circular buffer.  So if this call
        # is changed to accept the camera in the future, that should be kept in mind.
        self._mmc.startSequenceAcquisition(
            n_events,
            0,  # intervalMS  # TODO: add support for this
            True,  # stopOnOverflow
        )

        # block until the sequence is done, popping images in the meantime
        images = []
        while self._mmc.isSequenceRunning():
            if self._mmc.getRemainingImageCount():
                # TODO: pop with Metadata
                # see https://github.com/pymmcore-plus/pymmcore-plus/issues/220
                images.append(self._mmc.popNextImage())
            else:
                time.sleep(0.001)

        if self._mmc.isBufferOverflowed():  # pragma: no cover
            raise MemoryError("Buffer overflowed")

        while self._mmc.getRemainingImageCount():
            images.append(self._mmc.popNextImage())

        if len(images) != n_events:
            logger.warning(
                "Unexpected number of images returned from sequence. "
                "Expected %s, got %s",
                n_events,
                len(images),
            )

        return EventPayload(image_sequence=tuple(zip(images, event.events)))

    # ===================== EXTRA =====================

    def _execute_autofocus(self, action: HardwareAutofocus) -> float:
        """Perform the hardware autofocus.

        Returns the change in ZPosition that occurred during the autofocus event.
        """
        # switch off autofocus device if it is on
        self._mmc.enableContinuousFocus(False)

        # setup the autofocus device
        self._mmc.setPosition(
            action.autofocus_device_name,
            action.autofocus_motor_offset,
        )
        self._mmc.waitForSystem()

        @retry(exceptions=RuntimeError, tries=action.max_retries, logger=logger.warning)
        def _perform_full_focus(previous_z: float) -> float:
            self._mmc.fullFocus()
            self._mmc.waitForSystem()
            return self._mmc.getZPosition() - previous_z

        return _perform_full_focus(self._mmc.getZPosition())

    def _set_event_position(self, event: MDAEvent) -> None:
        # skip if no XY stage device is found
        if not self._mmc.getXYStageDevice():
            logger.warning("No XY stage device found. Cannot set XY position.")
            return

        x = event.x_pos if event.x_pos is not None else self._mmc.getXPosition()
        y = event.y_pos if event.y_pos is not None else self._mmc.getYPosition()
        self._mmc.setXYPosition(x, y)

    def _set_event_z(self, event: MDAEvent) -> None:
        # skip if no Z stage device is found
        if not self._mmc.getFocusDevice():
            logger.warning("No Z stage device found. Cannot set Z position.")
            return

        p_idx = event.index.get("p", None)
        correction = self._z_correction.setdefault(p_idx, 0.0)
        self._mmc.setZPosition(cast("float", event.z_pos) + correction)


class EventPayload(NamedTuple):
    image: np.ndarray | None = None
    image_sequence: Sequence[tuple[np.ndarray, MDAEvent]] | None = None
