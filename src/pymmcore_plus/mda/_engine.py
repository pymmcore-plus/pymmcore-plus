from __future__ import annotations

import time
import warnings
import weakref
from contextlib import suppress
from functools import cache
from itertools import product
from typing import TYPE_CHECKING, Literal, NamedTuple, cast

import numpy as np
import useq
from useq import AcquireImage, HardwareAutofocus, MDAEvent, MDASequence

from pymmcore_plus._logger import logger
from pymmcore_plus._util import retry
from pymmcore_plus.core._constants import FocusDirection, Keyword
from pymmcore_plus.core._sequencing import SequencedEvent, iter_sequenced_events
from pymmcore_plus.metadata import (
    FrameMetaV1,
    PropertyValue,
    SummaryMetaV1,
    frame_metadata,
    summary_metadata,
)

from ._protocol import PMDAEngine

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence
    from typing import TypeAlias

    from numpy.typing import NDArray
    from typing_extensions import TypedDict

    from pymmcore_plus.core import CMMCorePlus

    from ._protocol import PImagePayload

    IncludePositionArg: TypeAlias = Literal[True, False, "unsequenced-only"]

    class StateDict(TypedDict, total=False):
        xy_position: Sequence[float]
        z_position: float
        exposure: float
        autoshutter: bool
        config_groups: dict[str, str]


# these are SLM devices that have a known pixel_on_value.
# there is currently no way to extract this information from the core,
# so it is hard-coded here.
# maps device_name -> pixel_on_value
_SLM_DEVICES_PIXEL_ON_VALUES: dict[str, int] = {
    "MightexPolygon1000": 255,
    "Mosaic3": 1,
    "GenericSLM": 255,
}


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
        By default, this is `True`, however in various testing and demo scenarios, you
        may wish to set it to `False` in order to avoid unexpected behavior.
    restore_initial_state : bool | None
        Whether to restore the initial hardware state after the MDA sequence completes.
        If `True`, the engine will capture the initial state (positions,
        config groups, exposure settings) before the sequence starts and restore it
        after completion.  If `None` (the default), `restore_initial_state` will
        be set to `True` if FocusDirection is known (i.e. not Unknown).
    """

    def __init__(
        self,
        mmc: CMMCorePlus,
        *,
        use_hardware_sequencing: bool = True,
        restore_initial_state: bool | None = None,
    ) -> None:
        self._mmcore_ref = weakref.ref(mmc)
        self.use_hardware_sequencing: bool = use_hardware_sequencing
        # if True, always set XY position, even if the commanded position is the same
        # as the last commanded position (this does *not* query the stage for the
        # current position).
        self.force_set_xy_position: bool = True

        # whether to include position metadata when fetching on-frame metadata
        # omitted by default when performing triggered acquisition because it's slow.
        self._include_frame_position_metadata: IncludePositionArg = "unsequenced-only"

        # whether to restore the initial hardware state after sequence completion
        self.restore_initial_state: bool | None = restore_initial_state

        # stored initial state for restoration (if restore_initial_state is True)
        self._initial_state: StateDict = {}

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
        self._autoshutter_was_set: bool = mmc.getAutoShutter()

        self._last_config: tuple[str, str] = ("", "")
        self._last_xy_pos: tuple[float | None, float | None] = (None, None)

        # -----
        # The following values are stored during setup_sequence simply to speed up
        # retrieval of metadata during each frame.
        # sequence of (device, property) of all properties used in any of the presets
        # in the channel group.
        self._config_device_props: dict[str, Sequence[tuple[str, str]]] = {}

    @property
    def include_frame_position_metadata(self) -> IncludePositionArg:
        return self._include_frame_position_metadata

    @include_frame_position_metadata.setter
    def include_frame_position_metadata(self, value: IncludePositionArg) -> None:
        if value not in (True, False, "unsequenced-only"):  # pragma: no cover
            raise ValueError(
                "include_frame_position_metadata must be True, False, or "
                "'unsequenced-only'"
            )
        self._include_frame_position_metadata = value

    @property
    def mmcore(self) -> CMMCorePlus:
        """The `CMMCorePlus` instance to use for hardware control."""
        if (mmc := self._mmcore_ref()) is None:  # pragma: no cover
            raise RuntimeError("The CMMCorePlus instance has been garbage collected.")
        return mmc

    # ===================== Protocol Implementation =====================

    def setup_sequence(self, sequence: MDASequence) -> SummaryMetaV1 | None:
        """Setup the hardware for the entire sequence."""
        # clear z_correction for new sequence
        self._z_correction.clear()

        if not (core := self._mmcore_ref()):  # pragma: no cover
            from pymmcore_plus.core import CMMCorePlus

            core = CMMCorePlus.instance()
            self._mmcore_ref = weakref.ref(core)

        # just in case a non-programmatic changes have been made in the meantime
        # https://github.com/pymmcore-plus/pymmcore-plus/issues/503
        core._last_config = ("", "")  # noqa: SLF001
        core._last_xy_position.clear()  # noqa: SLF001

        self._update_config_device_props()
        # get if the autofocus is engaged at the start of the sequence
        self._af_was_engaged = core.isContinuousFocusLocked()

        # capture initial state if restoration is enabled
        if self.restore_initial_state is None:
            fd = core.getFocusDevice()
            self.restore_initial_state = (
                fd is not None and core.getFocusDirection(fd) != FocusDirection.Unknown
            )

        if self.restore_initial_state:
            self._initial_state = self._capture_state()

        if px_size := core.getPixelSizeUm():
            self._update_grid_fov_sizes(px_size, sequence)

        self._autoshutter_was_set = core.getAutoShutter()
        return self.get_summary_metadata(mda_sequence=sequence)

    def get_summary_metadata(self, mda_sequence: MDASequence | None) -> SummaryMetaV1:
        return summary_metadata(self.mmcore, mda_sequence=mda_sequence)

    def _update_grid_fov_sizes(self, px_size: float, sequence: MDASequence) -> None:
        *_, x_size, y_size = self.mmcore.getROI()
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
        self.mmcore.waitForSystem()

    def exec_event(self, event: MDAEvent) -> Iterable[PImagePayload]:
        """Execute an individual event and return the image data."""
        action = getattr(event, "action", None)
        core = self.mmcore
        if isinstance(action, HardwareAutofocus):
            # skip if no autofocus device is found
            if not core.getAutoFocusDevice():
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

        # don't try to execute any other action types. Mostly, this is just
        # CustomAction, which is a user-defined action that the engine doesn't know how
        # to handle.  But may include other actions in the future, and this ensures
        # backwards compatibility.
        if not isinstance(action, (AcquireImage, type(None))):
            return

        # if the autofocus was engaged at the start of the sequence AND autofocus action
        # did not fail, re-engage it. NOTE: we need to do that AFTER the runner calls
        # `setup_event`, so we can't do it inside the exec_event autofocus action above.
        if self._af_was_engaged and self._af_succeeded:
            core.enableContinuousFocus(True)

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

        yield from iter_sequenced_events(self.mmcore, events)

    # ===================== Regular Events =====================

    def setup_single_event(self, event: MDAEvent) -> None:
        """Setup hardware for a single (non-sequenced) event.

        This method is not part of the PMDAEngine protocol (it is called by
        `setup_event`, which *is* part of the protocol), but it is made public
        in case a user wants to subclass this engine and override this method.
        """
        if event.keep_shutter_open:
            ...

        self._set_event_xy_position(event)

        if event.z_pos is not None:
            self._set_event_z(event)
        if event.slm_image is not None:
            self._set_event_slm_image(event)

        self._set_event_channel(event)

        mmcore = self.mmcore
        if event.exposure is not None:
            try:
                mmcore.setExposure(event.exposure)
            except Exception as e:
                logger.warning("Failed to set exposure. %s", e)
        if event.properties is not None:
            try:
                for dev, prop, value in event.properties:
                    mmcore.setProperty(dev, prop, value)
            except Exception as e:
                logger.warning("Failed to set properties. %s", e)
        if (
            # (if autoshutter wasn't set at the beginning of the sequence
            # then it never matters...)
            self._autoshutter_was_set
            # if we want to leave the shutter open after this event, and autoshutter
            # is currently enabled...
            and event.keep_shutter_open
            and mmcore.getAutoShutter()
        ):
            # we have to disable autoshutter and open the shutter
            mmcore.setAutoShutter(False)
            mmcore.setShutterOpen(True)

    def exec_single_event(self, event: MDAEvent) -> Iterator[PImagePayload]:
        """Execute a single (non-triggered) event and return the image data.

        This method is not part of the PMDAEngine protocol (it is called by
        `exec_event`, which *is* part of the protocol), but it is made public
        in case a user wants to subclass this engine and override this method.
        """
        if event.slm_image is not None:
            self._exec_event_slm_image(event.slm_image)

        mmcore = self.mmcore
        try:
            mmcore.snapImage()
            # taking event time after snapImage includes exposure time
            # not sure that's what we want, but it's currently consistent with the
            # timing of the sequenced event runner (where Elapsed_Time_ms is taken after
            # the image is acquired, not before the exposure starts)
            t0 = event.metadata.get("runner_t0") or time.perf_counter()
            event_time_ms = (time.perf_counter() - t0) * 1000
        except Exception as e:
            logger.warning("Failed to snap image. %s", e)
            return
        if not event.keep_shutter_open:
            mmcore.setShutterOpen(False)

        # most cameras will only have a single channel
        # but Multi-camera may have multiple, and we need to retrieve a buffer for each
        for cam in range(mmcore.getNumberOfCameraChannels()):
            meta = self.get_frame_metadata(
                event,
                runner_time_ms=event_time_ms,
                camera_device=mmcore.getPhysicalCameraDevice(cam),
                include_position=self._include_frame_position_metadata is not False,
            )
            # Note, the third element is actually a MutableMapping, but mypy doesn't
            # see TypedDict as a subclass of MutableMapping yet.
            # https://github.com/python/mypy/issues/4976
            yield ImagePayload(mmcore.getImage(cam), event, meta)  # type: ignore[misc]

    def get_frame_metadata(
        self,
        event: MDAEvent,
        prop_values: tuple[PropertyValue, ...] | None = None,
        runner_time_ms: float = 0.0,
        include_position: bool = True,
        camera_device: str | None = None,
    ) -> FrameMetaV1:
        if prop_values is None and (ch := event.channel):
            prop_values = self._get_current_props(ch.group)
        else:
            prop_values = ()
        return frame_metadata(
            self.mmcore,
            cached=True,
            runner_time_ms=runner_time_ms,
            camera_device=camera_device,
            property_values=prop_values,
            mda_event=event,
            include_position=include_position,
        )

    def teardown_event(self, event: MDAEvent) -> None:
        """Teardown state of system (hardware, etc.) after `event`."""
        # autoshutter was set at the beginning of the sequence, and this event
        # doesn't want to leave the shutter open.  Re-enable autoshutter.
        core = self.mmcore
        if not event.keep_shutter_open and self._autoshutter_was_set:
            core.setAutoShutter(True)
        # FIXME: this may not be hitting as intended...
        # https://github.com/pymmcore-plus/pymmcore-plus/pull/353#issuecomment-2159176491
        if isinstance(event, SequencedEvent):
            if event.exposure_sequence:
                core.stopExposureSequence(core.getCameraDevice())
            if event.x_sequence:
                core.stopXYStageSequence(core.getXYStageDevice())
            if event.z_sequence:
                core.stopStageSequence(core.getFocusDevice())
            for dev, prop in event.property_sequences:
                core.stopPropertySequence(dev, prop)

    def teardown_sequence(self, sequence: MDASequence) -> None:
        """Perform any teardown required after the sequence has been executed."""
        # restore initial state if enabled and state was captured
        if self.restore_initial_state and self._initial_state:
            self._restore_initial_state()

    def _capture_state(self) -> StateDict:
        """Capture the current hardware state for later restoration."""
        state: StateDict = {}
        if (core := self._mmcore_ref()) is None:
            return state

        try:
            # capture XY position
            if core.getXYStageDevice():
                state["xy_position"] = core.getXYPosition()
        except Exception as e:
            logger.warning("Failed to capture XY position: %s", e)

        try:
            # capture Z position
            if core.getFocusDevice():
                state["z_position"] = core.getZPosition()
        except Exception as e:
            logger.warning("Failed to capture Z position: %s", e)

        try:
            state["exposure"] = core.getExposure()
        except Exception as e:
            logger.warning("Failed to capture exposure setting: %s", e)

        # capture config group states
        try:
            state_groups = state.setdefault("config_groups", {})
            for group in core.getAvailableConfigGroups():
                if current_config := core.getCurrentConfig(group):
                    state_groups[group] = current_config
        except Exception as e:
            logger.warning("Failed to get available config groups: %s", e)

        # capture autoshutter state
        try:
            state["autoshutter"] = core.getAutoShutter()
        except Exception as e:
            logger.warning("Failed to capture autoshutter state: %s", e)

        return state

    def _restore_initial_state(self) -> None:
        """Restore the hardware state that was captured before the sequence."""
        if not self._initial_state or (core := self._mmcore_ref()) is None:
            return

        # !!! We need to be careful about the order of Z and XY restoration:
        #
        # If FocusDirection is Unknown, we cannot safely restore Z *or* XY stage
        # positions: we simply refuse and warn.
        #
        # If focus_dir is TowardSample, and we are restoring a Z-position that is
        # *lower* than the current position or
        # if focus_dir is AwayFromSample, and we are restoring a Z-position that is
        # *higher* than the current position, then we need to move Z *before* moving XY,
        # otherwise we may crash the objective into the sample.
        # Otherwise, we should move XY first, then Z.
        target_z = self._initial_state.get("z_position")
        move_z_first = False
        focus_dir = FocusDirection.Unknown
        if target_z is not None and (focus_device := core.getFocusDevice()):
            focus_dir = core.getFocusDirection(focus_device)
            cur_z = core.getZPosition()
            # focus_dir TowardSample => increasing position brings obj. closer to sample
            if cur_z > target_z:
                if focus_dir == FocusDirection.TowardSample:
                    move_z_first = True
            elif focus_dir == FocusDirection.AwayFromSample:
                move_z_first = True

        if focus_dir == FocusDirection.Unknown:
            _warn_focus_dir(focus_device)
        else:

            def _move_z() -> None:
                if target_z is not None:
                    try:
                        if core.getFocusDevice():
                            core.setZPosition(target_z)
                    except Exception as e:
                        logger.warning("Failed to restore Z position: %s", e)

            if move_z_first:
                _move_z()

            # restore XY position
            if "xy_position" in self._initial_state:
                try:
                    if core.getXYStageDevice():
                        core.setXYPosition(*self._initial_state["xy_position"])
                except Exception as e:
                    logger.warning("Failed to restore XY position: %s", e)

            if not move_z_first:
                _move_z()

        # restore exposure
        if "exposure" in self._initial_state:
            try:
                core.setExposure(self._initial_state["exposure"])
            except Exception as e:
                logger.warning("Failed to restore exposure setting: %s", e)

        # restore config group states
        for key, value in self._initial_state.get("config_groups", {}).items():
            try:
                core.setConfig(key, value)
            except Exception as e:
                logger.warning(
                    "Failed to restore config group %s to %s: %s", key, value, e
                )

        # restore autoshutter state
        if "autoshutter" in self._initial_state:
            try:
                core.setAutoShutter(self._initial_state["autoshutter"])
            except Exception as e:
                logger.warning("Failed to restore autoshutter state: %s", e)

        core.waitForSystem()
        # clear the state after restoration
        self._initial_state = {}

    # ===================== Sequenced Events =====================

    def _load_sequenced_event(self, event: SequencedEvent) -> None:
        """Load a `SequencedEvent` into the core.

        `SequencedEvent` is a special pymmcore-plus specific subclass of
        `useq.MDAEvent`.
        """
        core = self.mmcore
        if event.exposure_sequence:
            cam_device = core.getCameraDevice()
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
        if event.slm_sequence:
            slm = core.getSLMDevice()
            with suppress(RuntimeError):
                core.stopSLMSequence(slm)
            core.loadSLMSequence(slm, event.slm_sequence)  # type: ignore[arg-type]
        if event.property_sequences:
            for (dev, prop), value_sequence in event.property_sequences.items():
                with suppress(RuntimeError):
                    core.stopPropertySequence(dev, prop)
                core.loadPropertySequence(dev, prop, value_sequence)

        # set all static properties, these won't change over the course of the sequence.
        if event.properties:
            for dev, prop, value in event.properties:
                core.setProperty(dev, prop, value)

    def setup_sequenced_event(self, event: SequencedEvent) -> None:
        """Setup hardware for a sequenced (triggered) event.

        This method is not part of the PMDAEngine protocol (it is called by
        `setup_event`, which *is* part of the protocol), but it is made public
        in case a user wants to subclass this engine and override this method.
        """
        core = self.mmcore

        self._load_sequenced_event(event)

        # this is probably not necessary.  loadSequenceEvent will have already
        # set all the config properties individually/manually.  However, without
        # the call below, we won't be able to query `core.getCurrentConfig()`
        # not sure that's necessary; and this is here for tests to pass for now,
        # but this could be removed.
        self._set_event_channel(event)

        if event.slm_image:
            self._set_event_slm_image(event)

        # preparing a Sequence while another is running is dangerous.
        if core.isSequenceRunning():
            self._await_sequence_acquisition()
        core.prepareSequenceAcquisition(core.getCameraDevice())

        # start sequences or set non-sequenced values
        if event.x_sequence:
            core.startXYStageSequence(core.getXYStageDevice())
        else:
            self._set_event_xy_position(event)

        if event.z_sequence:
            core.startStageSequence(core.getFocusDevice())
        elif event.z_pos is not None:
            self._set_event_z(event)

        if event.exposure_sequence:
            core.startExposureSequence(core.getCameraDevice())
        elif event.exposure is not None:
            core.setExposure(event.exposure)

        if event.property_sequences:
            for dev, prop in event.property_sequences:
                core.startPropertySequence(dev, prop)

    def _await_sequence_acquisition(
        self, timeout: float = 5.0, poll_interval: float = 0.2
    ) -> None:
        tot = 0.0
        core = self.mmcore
        core.stopSequenceAcquisition()
        while core.isSequenceRunning():
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

        t0 = event.metadata.get("runner_t0") or time.perf_counter()
        event_t0_ms = (time.perf_counter() - t0) * 1000

        if event.slm_image is not None:
            self._exec_event_slm_image(event.slm_image)

        core = self.mmcore
        # Start sequence
        # Note that the overload of startSequenceAcquisition that takes a camera
        # label does NOT automatically initialize a circular buffer.  So if this call
        # is changed to accept the camera in the future, that should be kept in mind.
        core.startSequenceAcquisition(
            n_events,
            0,  # intervalMS  # TODO: add support for this
            True,  # stopOnOverflow
        )
        self.post_sequence_started(event)

        n_channels = core.getNumberOfCameraChannels()
        count = 0
        iter_events = product(event.events, range(n_channels))

        # to make sure we emit the cancel log only once
        cancel_logged = False

        # block until the sequence is done, popping images in the meantime
        while core.isSequenceRunning():
            # NOTE: there is not a way to pause a hardware sequence acquisition.
            if core.mda.is_paused():
                logger.warning(
                    "Pause has been requested, but sequenced acquisition "
                    "cannot be yet paused."
                )

            # check if acquisition is canceled
            if core.mda.is_canceled():
                core.stopSequenceAcquisition()
                logger.warning("MDA Canceled: %s", event)
                cancel_logged = True
                return

            if remaining := core.getRemainingImageCount():
                yield self._next_seqimg_payload(
                    *next(iter_events), remaining=remaining - 1, event_t0=event_t0_ms
                )
                count += 1
            else:
                time.sleep(0.001)

        if core.isBufferOverflowed():  # pragma: no cover
            raise MemoryError("Buffer overflowed")

        while remaining := core.getRemainingImageCount():

            # check if acquisition is canceled
            if core.mda.is_canceled():
                if not cancel_logged:
                    logger.warning("MDA Canceled: %s", event)
                return

            yield self._next_seqimg_payload(
                *next(iter_events), remaining=remaining - 1, event_t0=event_t0_ms
            )
            count += 1

        # necessary?
        expected_images = n_events * n_channels
        if count != expected_images:
            logger.warning(
                "Unexpected number of images returned from sequence. "
                "Expected %s, got %s",
                expected_images,
                count,
            )

    def _next_seqimg_payload(
        self,
        event: MDAEvent,
        channel: int = 0,
        *,
        event_t0: float = 0.0,
        remaining: int = 0,
    ) -> PImagePayload:
        """Grab next image from the circular buffer and return it as an ImagePayload."""
        _slice = 0  # ?
        core = self.mmcore
        img, mm_meta = core.popNextImageAndMD(channel, _slice)
        try:
            seq_time = float(mm_meta.get(Keyword.Elapsed_Time_ms))
        except Exception:
            seq_time = 0.0
        try:
            # note, when present in circular buffer meta, this key is called "Camera".
            # It's NOT actually Keyword.CoreCamera (but it's the same value)
            # it is hardcoded in various places in mmCoreAndDevices, see:
            # see: https://github.com/micro-manager/mmCoreAndDevices/pull/468
            camera_device = mm_meta.GetSingleTag("Camera").GetValue()
        except Exception:
            camera_device = core.getPhysicalCameraDevice(channel)

        # TODO: determine whether we want to try to populate changing property values
        # during the course of a triggered sequence
        meta = self.get_frame_metadata(
            event,
            prop_values=(),
            runner_time_ms=event_t0 + seq_time,
            camera_device=camera_device,
            include_position=self._include_frame_position_metadata is True,
        )
        meta["hardware_triggered"] = True
        meta["images_remaining_in_buffer"] = remaining
        meta["camera_metadata"] = dict(mm_meta)

        # https://github.com/python/mypy/issues/4976
        return ImagePayload(img, event, meta)  # type: ignore[return-value]

    # ===================== EXTRA =====================

    def _execute_autofocus(self, action: HardwareAutofocus) -> float:
        """Perform the hardware autofocus.

        Returns the change in ZPosition that occurred during the autofocus event.
        """
        core = self.mmcore
        # switch off autofocus device if it is on
        core.enableContinuousFocus(False)

        if action.autofocus_motor_offset is not None:
            # set the autofocus device offset
            # if name is given explicitly, use it, otherwise use setAutoFocusOffset
            # (see docs for setAutoFocusOffset for additional details)
            if name := getattr(action, "autofocus_device_name", None):
                core.setPosition(name, action.autofocus_motor_offset)
            else:
                core.setAutoFocusOffset(action.autofocus_motor_offset)
            core.waitForSystem()

        @retry(exceptions=RuntimeError, tries=action.max_retries, logger=logger.warning)
        def _perform_full_focus(previous_z: float) -> float:
            core.fullFocus()
            core.waitForSystem()
            return core.getZPosition() - previous_z

        return _perform_full_focus(core.getZPosition())

    def _set_event_xy_position(self, event: MDAEvent) -> None:
        event_x, event_y = event.x_pos, event.y_pos
        # If neither coordinate is provided, do nothing.
        if event_x is None and event_y is None:
            return

        core = self.mmcore
        # skip if no XY stage device is found
        if not core.getXYStageDevice():
            logger.warning("No XY stage device found. Cannot set XY position.")
            return

        # Retrieve the last commanded XY position.
        last_x, last_y = core._last_xy_position.get(None) or (None, None)  # noqa: SLF001
        if (
            not self.force_set_xy_position
            and (event_x is None or event_x == last_x)
            and (event_y is None or event_y == last_y)
        ):
            return

        if event_x is None or event_y is None:
            cur_x, cur_y = core.getXYPosition()
            event_x = cur_x if event_x is None else event_x
            event_y = cur_y if event_y is None else event_y

        try:
            core.setXYPosition(event_x, event_y)
        except Exception as e:
            logger.warning("Failed to set XY position. %s", e)

    def _set_event_channel(self, event: MDAEvent) -> None:
        if (ch := event.channel) is None:
            return

        # comparison with _last_config is a fast/rough check ... which may miss subtle
        # differences if device properties have been individually set in the meantime.
        # could also compare to the system state, with:
        # data = self.mmcore.getConfigData(ch.group, ch.config)
        # if self.mmcore.getSystemStateCache().isConfigurationIncluded(data):
        #     ...
        if (ch.group, ch.config) != self.mmcore._last_config:  # noqa: SLF001
            try:
                self.mmcore.setConfig(ch.group, ch.config)
            except Exception as e:
                logger.warning("Failed to set channel. %s", e)

    def _set_event_z(self, event: MDAEvent) -> None:
        # skip if no Z stage device is found
        if not self.mmcore.getFocusDevice():
            logger.warning("No Z stage device found. Cannot set Z position.")
            return

        p_idx = event.index.get("p", None)
        correction = self._z_correction.setdefault(p_idx, 0.0)
        self.mmcore.setZPosition(cast("float", event.z_pos) + correction)

    def _set_event_slm_image(self, event: MDAEvent) -> None:
        if not event.slm_image:
            return
        core = self.mmcore
        try:
            # Get the SLM device
            if not (
                slm_device := event.slm_image.device or core.getSLMDevice()
            ):  # pragma: no cover
                raise ValueError("No SLM device found or specified.")

            # cast to numpy array
            slm_array = np.asarray(event.slm_image)
            # if it's a single value, we can just set all pixels to that value
            if slm_array.ndim == 0:
                value = slm_array.item()
                if isinstance(value, bool):
                    dev_name = core.getDeviceName(slm_device)
                    on_value = _SLM_DEVICES_PIXEL_ON_VALUES.get(dev_name, 1)
                    value = on_value if value else 0
                core.setSLMPixelsTo(slm_device, int(value))
            elif slm_array.size == 3:
                # if it's a 3-valued array, we assume it's RGB
                r, g, b = slm_array.astype(int)
                core.setSLMPixelsTo(slm_device, r, g, b)
            elif slm_array.ndim in (2, 3):
                # if it's a 2D/3D array, we assume it's an image
                # where 3D is RGB with shape (h, w, 3)
                if slm_array.ndim == 3 and slm_array.shape[2] != 3:
                    raise ValueError(  # pragma: no cover
                        "SLM image must be 2D or 3D with 3 channels (RGB)."
                    )
                # convert boolean on/off values to pixel values
                if slm_array.dtype == bool:
                    dev_name = core.getDeviceName(slm_device)
                    on_value = _SLM_DEVICES_PIXEL_ON_VALUES.get(dev_name, 1)
                    slm_array = np.where(slm_array, on_value, 0).astype(np.uint8)
                core.setSLMImage(slm_device, slm_array)
            if event.slm_image.exposure:
                core.setSLMExposure(slm_device, event.slm_image.exposure)
        except Exception as e:
            logger.warning("Failed to set SLM Image: %s", e)

    def _exec_event_slm_image(self, img: useq.SLMImage) -> None:
        if slm_device := (img.device or self.mmcore.getSLMDevice()):
            try:
                self.mmcore.displaySLMImage(slm_device)
            except Exception as e:
                logger.warning("Failed to set SLM Image: %s", e)

    def _update_config_device_props(self) -> None:
        # store devices/props that make up each config group for faster lookup
        self._config_device_props.clear()
        core = self.mmcore
        for grp in core.getAvailableConfigGroups():
            for preset in core.getAvailableConfigs(grp):
                # ordered/unique list of (device, property) tuples for each group
                self._config_device_props[grp] = tuple(
                    {(i[0], i[1]): None for i in core.getConfigData(grp, preset)}
                )

    def _get_current_props(self, *groups: str) -> tuple[PropertyValue, ...]:
        """Faster version of core.getConfigGroupState(group).

        MMCore does some excess iteration that we want to avoid here. It calls
        GetAvailableConfigs and then calls getConfigData for *every* preset in the
        group, (not only the one being requested).  We go straight to cached data
        for the group we want.
        """
        return tuple(
            {
                "dev": dev,
                "prop": prop,
                "val": self.mmcore.getPropertyFromCache(dev, prop),
            }
            for group in groups
            if (dev_props := self._config_device_props.get(group))
            for dev, prop in dev_props
        )


class ImagePayload(NamedTuple):
    image: NDArray
    event: MDAEvent
    metadata: FrameMetaV1 | SummaryMetaV1


@cache
def _warn_focus_dir(focus_device: str) -> None:
    warnings.warn(
        "Focus direction is unknown: refusing to restore initial XYZ position "
        "for safety reasons. Please set FocusDirection in your config file:\n\n"
        f"  FocusDirection,{focus_device},<1 or -1>\n\n"
        "Or use the `Hardware Configuration Wizard > Stage Focus Direction`",
        stacklevel=3,
        category=RuntimeWarning,
    )
