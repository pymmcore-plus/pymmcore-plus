from __future__ import annotations

import time
from contextlib import suppress
from itertools import product
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    Iterator,
    NamedTuple,
    Sequence,
    cast,
)

from useq import HardwareAutofocus, MDAEvent, MDASequence

from pymmcore_plus._logger import logger
from pymmcore_plus._util import retry
from pymmcore_plus.core._constants import Keyword, PymmcPlusConstants
from pymmcore_plus.core._sequencing import SequencedEvent
from pymmcore_plus.mda.metadata._structs import FrameMetaV1, SummaryMetaV1
from pymmcore_plus.mda.metadata.metadata import (
    ensure_valid_metadata_func,
    get_metadata_func,
)

from ._protocol import PMDAEngine

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from pymmcore_plus.core import CMMCorePlus
    from pymmcore_plus.core._metadata import Metadata
    from pymmcore_plus.mda.metadata.metadata import MetaDataGetter

    from ._protocol import PImagePayload


class MDAEngine(PMDAEngine):
    """The default MDAengine that ships with pymmcore-plus.

    This implements the [`PMDAEngine`][pymmcore_plus.mda.PMDAEngine] protocol, and
    uses a [`CMMCorePlus`][pymmcore_plus.CMMCorePlus] instance to control the hardware.

    It may be subclassed to provide custom behavior, or to override specific methods.
    <https://pymmcore-plus.github.io/pymmcore-plus/guides/custom_engine/>

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

    _get_summary_meta: MetaDataGetter
    _get_frame_meta: MetaDataGetter

    def __init__(
        self,
        mmc: CMMCorePlus,
        *,
        use_hardware_sequencing: bool = False,
        summary_metadata_format: str | MetaDataGetter = SummaryMetaV1.from_core,
        summary_metadata_version: str = "1.0",
        frame_metadata_format: str | MetaDataGetter = FrameMetaV1.from_core,
        frame_metadata_version: str = "1.0",
    ) -> None:
        self._mmc = mmc
        self.use_hardware_sequencing = use_hardware_sequencing
        self.set_summary_metadata_format(
            summary_metadata_format, summary_metadata_version
        )
        self.set_frame_metadata_format(frame_metadata_format, frame_metadata_version)

        # used to check if the hardware autofocus is engaged when the sequence begins.
        # if it is, we will re-engage it after the autofocus action (if successful).
        self._af_was_engaged: bool = False
        # used to store the success of the last _execute_autofocus call
        self._af_succeeded: bool = False

        # used for one_shot autofocus to store the z correction for each position index.
        # map of {position_index: z_correction}
        self._z_correction: dict[int | None, float] = {}

        # This is used to determine whether we need to re-enable autoshutter after
        # the sequence is done (assuming a event.keep_shutter_open was requested)
        # Note: getAutoShutter() is True when no config is loaded at all
        self._autoshutter_was_set: bool = self._mmc.getAutoShutter()

        # -----
        # The following values are stored during setup_sequence simply to speed up
        # retrieval of metadata during each frame.
        # sequence of (device, property) of all properties used in any of the presets
        # in the channel group.
        self._config_device_props: dict[str, Sequence[tuple[str, str]]] = {}

    @property
    def mmcore(self) -> CMMCorePlus:
        """The `CMMCorePlus` instance to use for hardware control."""
        return self._mmc

    def set_summary_metadata_format(
        self, format: str | MetaDataGetter, version: str
    ) -> None:
        """Set the format and version for the summary metadata."""
        if isinstance(format, str):
            self._get_summary_meta = get_metadata_func(format, version)
        else:
            self._get_summary_meta = ensure_valid_metadata_func(format)

    def set_frame_metadata_format(
        self, format: str | MetaDataGetter, version: str
    ) -> None:
        """Set the format and version for the frame metadata."""
        if isinstance(format, str):
            self._get_frame_meta = get_metadata_func(format, version)
        else:
            self._get_frame_meta = ensure_valid_metadata_func(format)

    # ===================== Protocol Implementation =====================

    def setup_sequence(self, sequence: MDASequence) -> Any:
        """Setup the hardware for the entire sequence."""
        # clear z_correction for new sequence
        self._z_correction.clear()

        if not self._mmc:  # pragma: no cover
            from pymmcore_plus.core import CMMCorePlus

            self._mmc = CMMCorePlus.instance()

        self._update_config_device_props()
        # get if the autofocus is engaged at the start of the sequence
        self._af_was_engaged = self._mmc.isContinuousFocusLocked()

        if px_size := self._mmc.getPixelSizeUm():
            self._update_grid_fov_sizes(px_size, sequence)

        self._autoshutter_was_set = self._mmc.getAutoShutter()
        return self.get_summary_metadata(
            {PymmcPlusConstants.MDA_SEQUENCE.value: sequence}
        )

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

    def exec_event(self, event: MDAEvent) -> Iterable[PImagePayload]:
        """Execute an individual event and return the image data."""
        action = getattr(event, "action", None)
        if isinstance(action, HardwareAutofocus):
            # skip if no autofocus device is found
            if not self._mmc.getAutoFocusDevice():
                logger.warning("No autofocus device found. Cannot execute autofocus.")
                return

            try:
                # execute hardware autofocus
                new_correction = self._execute_autofocus(action)
                self._af_succeeded = True
            except RuntimeError as e:
                logger.warning("Hardware autofocus failed. %s", e)
                self._af_succeeded = False
            else:
                # store correction for this position index
                p_idx = event.index.get("p", None)
                self._z_correction[p_idx] = new_correction + self._z_correction.get(
                    p_idx, 0.0
                )
            return

        # if the autofocus was engaged at the start of the sequence AND autofocus action
        # did not fail, re-engage it. NOTE: we need to do that AFTER the runner calls
        # `setup_event`, so we can't do it inside the exec_event autofocus action above.
        if self._af_was_engaged and self._af_succeeded:
            self._mmc.enableContinuousFocus(True)

        if isinstance(event, SequencedEvent):
            yield from self.exec_sequenced_event(event)
        else:
            yield from self.exec_single_event(event)

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

    def exec_single_event(self, event: MDAEvent) -> Iterator[PImagePayload]:
        """Execute a single (non-triggered) event and return the image data.

        This method is not part of the PMDAEngine protocol (it is called by
        `exec_event`, which *is* part of the protocol), but it is made public
        in case a user wants to subclass this engine and override this method.
        """
        try:
            self._mmc.snapImage()
        except Exception as e:
            logger.warning("Failed to snap image. %s", e)
            return
        if not event.keep_shutter_open:
            self._mmc.setShutterOpen(False)

        for cam in range(self._mmc.getNumberOfCameraChannels()):
            yield ImagePayload(
                self._mmc.getImage(cam),
                event,
                self.get_frame_metadata(event, cam_index=cam),
            )

    def get_summary_metadata(self, extra: dict | None = None) -> Any:
        return self._get_summary_meta(self._mmc, extra or {})

    def get_frame_metadata(
        self, event: MDAEvent, meta: Metadata | None = None, cam_index: int = 0
    ) -> Any:
        extra = {} if meta is None else dict(meta)
        extra[PymmcPlusConstants.MDA_EVENT.value] = event

        if (ch := event.channel) and (info := self._get_config_group_state(ch.group)):
            extra[PymmcPlusConstants.CONFIG_STATE.value] = {ch.group: info}
        if (key := Keyword.CoreCamera.value) not in extra:
            # note, when present in meta, this key is called "Camera".
            # It's NOT actually Keyword.CoreCamera (but it's the same value)
            # it is hardcoded in various places in mmCoreAndDevices, see:
            # see: https://github.com/micro-manager/mmCoreAndDevices/pull/468
            extra[key] = self._mmc.getPhysicalCameraDevice(cam_index)
        return self._get_frame_meta(self._mmc, extra)

    def teardown_event(self, event: MDAEvent) -> None:
        """Teardown state of system (hardware, etc.) after `event`."""
        # autoshutter was set at the beginning of the sequence, and this event
        # doesn't want to leave the shutter open.  Re-enable autoshutter.
        core = self._mmc
        if not event.keep_shutter_open and self._autoshutter_was_set:
            core.setAutoShutter(True)
        # FIXME: this may not be hitting as intended...
        # https://github.com/pymmcore-plus/pymmcore-plus/pull/353#issuecomment-2159176491
        if isinstance(event, SequencedEvent):
            if event.exposure_sequence:
                core.stopExposureSequence(self._mmc.getCameraDevice())
            if event.x_sequence:
                core.stopXYStageSequence(core.getXYStageDevice())
            if event.z_sequence:
                core.stopStageSequence(core.getFocusDevice())
            for dev, prop in event.property_sequences(core):
                core.stopPropertySequence(dev, prop)

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
            with suppress(RuntimeError):
                core.stopExposureSequence(cam_device)
            core.loadExposureSequence(cam_device, event.exposure_sequence)
        if event.x_sequence:  # y_sequence is implied and will be the same length
            stage = core.getXYStageDevice()
            with suppress(RuntimeError):
                core.stopXYStageSequence(stage)
            core.loadXYStageSequence(stage, event.x_sequence, event.y_sequence)
        if event.z_sequence:
            zstage = core.getFocusDevice()
            with suppress(RuntimeError):
                core.stopStageSequence(zstage)
            core.loadStageSequence(zstage, event.z_sequence)
        if prop_seqs := event.property_sequences(core):
            for (dev, prop), value_sequence in prop_seqs.items():
                with suppress(RuntimeError):
                    core.stopPropertySequence(dev, prop)
                core.loadPropertySequence(dev, prop, value_sequence)

        # TODO: SLM

        # preparing a Sequence while another is running is dangerous.
        if core.isSequenceRunning():
            self._await_sequence_acquisition()
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

    def _await_sequence_acquisition(
        self, timeout: float = 5.0, poll_interval: float = 0.2
    ) -> None:
        tot = 0.0
        self._mmc.stopSequenceAcquisition()
        while self._mmc.isSequenceRunning():
            time.sleep(poll_interval)
            tot += poll_interval
            if tot >= timeout:
                raise TimeoutError("Failed to stop running sequence")

    def post_sequence_started(self, event: SequencedEvent) -> None:
        """Perform any actions after startSequenceAcquisition has been called.

        This method is available to subclasses in case they need to perform any
        actions after a hardware-triggered sequence has been started (i.e. after
        core.startSequenceAcquisition has been called).

        The default implementation does nothing.
        """

    def exec_sequenced_event(self, event: SequencedEvent) -> Iterable[PImagePayload]:
        """Execute a sequenced (triggered) event and return the image data.

        This method is not part of the PMDAEngine protocol (it is called by
        `exec_event`, which *is* part of the protocol), but it is made public
        in case a user wants to subclass this engine and override this method.
        """
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
        self.post_sequence_started(event)

        n_channels = self._mmc.getNumberOfCameraChannels()
        count = 0
        iter_events = product(event.events, range(n_channels))
        # block until the sequence is done, popping images in the meantime
        while self._mmc.isSequenceRunning():
            if self._mmc.getRemainingImageCount():
                yield self._next_img_payload(*next(iter_events))
                count += 1
            else:
                time.sleep(0.001)

        if self._mmc.isBufferOverflowed():  # pragma: no cover
            raise MemoryError("Buffer overflowed")

        while self._mmc.getRemainingImageCount():
            yield self._next_img_payload(*next(iter_events))
            count += 1

        expected_images = n_events * n_channels
        if count != expected_images:
            logger.warning(
                "Unexpected number of images returned from sequence. "
                "Expected %s, got %s",
                expected_images,
                count,
            )

    def _next_img_payload(self, event: MDAEvent, channel: int = 0) -> PImagePayload:
        """Grab next image from the circular buffer and return it as an ImagePayload."""
        _slice = 0  # ?
        img, meta = self._mmc.popNextImageAndMD(channel, _slice)
        _meta = self.get_frame_metadata(event, meta)
        return ImagePayload(img, event, _meta)

    # ===================== EXTRA =====================

    def _execute_autofocus(self, action: HardwareAutofocus) -> float:
        """Perform the hardware autofocus.

        Returns the change in ZPosition that occurred during the autofocus event.
        """
        # switch off autofocus device if it is on
        self._mmc.enableContinuousFocus(False)

        if action.autofocus_motor_offset is not None:
            # set the autofocus device offset
            # if name is given explicitly, use it, otherwise use setAutoFocusOffset
            # (see docs for setAutoFocusOffset for additional details)
            if name := getattr(action, "autofocus_device_name", None):
                self._mmc.setPosition(name, action.autofocus_motor_offset)
            else:
                self._mmc.setAutoFocusOffset(action.autofocus_motor_offset)
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

    def _update_config_device_props(self) -> None:
        # store devices/props that make up each config group for faster lookup
        self._config_device_props.clear()
        for grp in self._mmc.getAvailableConfigGroups():
            for preset in self._mmc.getAvailableConfigs(grp):
                # ordered/unique list of (device, property) tuples for each group
                self._config_device_props[grp] = tuple(
                    {(i[0], i[1]): None for i in self._mmc.getConfigData(grp, preset)}
                )

    def _get_config_group_state(self, group: str) -> dict[str, dict[str, str]]:
        """Faster version of core.getConfigGroupState(group).

        MMCore does some excess iteration that we want to avoid here. It calls
        GetAvailableConfigs and then calls getConfigData for *every* preset in the
        group, (not only the one being requested).  We go straight to cached data
        for the group we want.
        """
        state: dict[str, dict[str, str]] = {}
        if group in self._config_device_props:
            for dev, prop in self._config_device_props[group]:
                dev_dict = state.setdefault(dev, {})
                dev_dict[prop] = self._mmc.getPropertyFromCache(dev, prop)
        return state


class ImagePayload(NamedTuple):
    image: NDArray
    event: MDAEvent
    metadata: Any
