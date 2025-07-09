from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Optional, TypeVar

from pydantic import Field, model_validator
from useq import AcquireImage, MDAEvent, MDASequence

from pymmcore_plus.core._constants import DeviceType, Keyword

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from typing import Self

    from useq._mda_event import Channel as EventChannel

    from pymmcore_plus import CMMCorePlus


T = TypeVar("T")

__all__ = ["SequencedEvent", "get_all_sequenceable", "iter_sequenced_events"]


def iter_sequenced_events(
    core: CMMCorePlus, events: Iterable[MDAEvent]
) -> Iterator[MDAEvent | SequencedEvent]:
    """Iterate over a sequence of MDAEvents, yielding SequencedEvents when possible.

    Parameters
    ----------
    core : CMMCorePlus
        The core object to use for determining sequenceable properties.
    events : Iterable[MDAEvent]
        The events to iterate over.

    Returns
    -------
    Iterator[MDAEvent | SequencedEvent]
        A new iterator that will combine multiple MDAEvents into a single SequencedEvent
        when possible, based on the sequenceable properties of the core object.
        Note that `SequencedEvent` itself is a subclass of `MDAEvent`, but it's up to
        the engine to check `isinstance(event, SequencedEvent)` in order to handle
        SequencedEvents differently.
    """
    combiner = EventCombiner(core)
    for e in events:
        if (flushed := combiner.feed_event(e)) is not None:
            yield flushed

    if (leftover := combiner.flush()) is not None:
        yield leftover


class SequencedEvent(MDAEvent):
    """Subclass of MDAEvent that represents a sequence of triggered events."""

    events: tuple[MDAEvent, ...] = Field(repr=False)

    exposure_sequence: tuple[float, ...] = Field(default_factory=tuple)
    x_sequence: tuple[float, ...] = Field(default_factory=tuple)
    y_sequence: tuple[float, ...] = Field(default_factory=tuple)
    z_sequence: tuple[float, ...] = Field(default_factory=tuple)
    slm_sequence: tuple[bytes, ...] = Field(default_factory=tuple)

    # re-defining this from MDAEvent to circumvent a strange issue with pydantic 2.11
    sequence: Optional[MDASequence] = Field(default=None, repr=False)  # noqa: UP045

    # all other property sequences
    property_sequences: dict[tuple[str, str], list[str]] = Field(default_factory=dict)
    # static properties should be added to MDAEvent.properties as usual

    @model_validator(mode="after")
    def _check_lengths(self) -> Self:
        if len(self.x_sequence) != len(self.y_sequence):
            raise ValueError("XY sequence lengths must match")
        return self

    def __repr_args__(self) -> Iterable[tuple[str | None, Any]]:
        for k, v in super().__repr_args__():
            if isinstance(v, tuple):
                v = f"({len(v)} items)"
            if isinstance(v, dict):
                v = f"({len(v)} items)"
            yield k, v


def get_all_sequenceable(
    core: CMMCorePlus, include_properties: bool = True
) -> dict[tuple[str | DeviceType, str], int]:
    """Return all sequenceable devices in `core`.

    This is just a convenience function to help determine which devices can be
    sequenced on a given configuration.

    Parameters
    ----------
    core : CMMCorePlus
        The core object to use for determining sequenceable properties.
    include_properties : bool
        Whether to check/include all device properties in the result.

    Returns
    -------
    dict[tuple[str | DeviceType, str], int]
        mapping of (device_name, prop_name) or (DeviceType, device_label) -> int
        where int is the max sequence length for that device.
        If the first item in the tupl is a DeviceType rather than a string, it implies
        one should use the corresponding sequencing method:
            DeviceType.Stage -> startStageSequence(device_label)
            DeviceType.XYStage -> startXYStageSequence(device_label)
            DeviceType.Camera -> startExposureSequence(device_label)
        otherwise use
            startPropertySequence(device_name, prop_name)
    """
    d: dict[tuple[str | DeviceType, str], int] = {}
    for device in core.iterDevices():
        if include_properties:
            for prop in device.properties:
                if prop.isSequenceable():
                    d[(prop.device, prop.name)] = prop.sequenceMaxLength()
        if device.type() == DeviceType.Stage:
            # isStageLinearSequenceable?
            if core.isStageSequenceable(device.label):
                max_len = core.getStageSequenceMaxLength(device.label)
                d[(DeviceType.Stage, device.label)] = max_len
        elif device.type() == DeviceType.XYStage:
            if core.isXYStageSequenceable(device.label):
                max_len = core.getXYStageSequenceMaxLength(device.label)
                d[(DeviceType.XYStage, device.label)] = max_len
        elif device.type() == DeviceType.Camera:
            if core.isExposureSequenceable(device.label):
                max_len = core.getExposureSequenceMaxLength(device.label)
                d[(DeviceType.Camera, device.label)] = max_len
    return d


# ==============================================


class EventCombiner:
    """Helper class to combine multiple MDAEvents into a single SequencedEvent.

    See also: `iter_sequenced_events`, which is the primary way that this class is used.

    Parameters
    ----------
    core : CMMCorePlus
        The core object to use for determining sequenceable properties
    """

    def __init__(self, core: CMMCorePlus) -> None:
        self.core = core
        self.max_lengths: dict[Keyword | tuple[str, str], int] = (
            _get_max_sequence_lengths(core)  # type: ignore [assignment]
        )

        # cached property values for each channel
        self._channel_props: dict[EventChannel, dict[tuple[str, str], Any]] = {}
        # cached max sequence lengths for each property
        self._prop_lengths: dict[tuple[str, str], int] = {}

        # growing list of MDAEvents to be combined into a single SequencedEvent
        self.event_batch: list[MDAEvent] = []

        # whether a given attribute has changed in the current batch
        self.attribute_changes: dict[Keyword | tuple[str, str], bool] = {}
        self.first_event_props: dict[tuple[str, str], Any] = {}
        self._reset_tracking()

    def _reset_tracking(self) -> None:
        self.event_batch.clear()
        self.attribute_changes.clear()
        self.first_event_props.clear()

    def feed_event(self, event: MDAEvent) -> MDAEvent | SequencedEvent | None:
        """Feed one new event into the combiner.

        Returns a flushed MDAEvent/SequencedEvent if the new event *cannot* extend the
        current batch, or `None` otherwise.
        """
        if not self.event_batch:
            # Starting a new batch
            self.event_batch.append(event)
            self.first_event_props = self._event_properties(event)
            return None

        if self.can_extend(event):
            # Extend the current batch
            self.event_batch.append(event)
            return None

        # we've hit the end of the sequence
        # first, flus the existing batch...
        flushed = self._create_sequenced_event()

        # Then start a new batch with this new event...
        self._reset_tracking()
        self.event_batch.append(event)
        self.first_event_props = self._event_properties(event)

        # then return the flushed event
        return flushed

    def can_extend(self, event: MDAEvent) -> bool:
        """Return True if the new event can be added to the current batch."""
        # cannot add pre-existing SequencedEvents to the sequence
        if not self.event_batch:
            return True

        e0 = self.event_batch[0]

        # cannot sequence on top of SequencedEvents
        if isinstance(e0, SequencedEvent) or isinstance(event, SequencedEvent):
            return False
        # cannot sequence on top of non-'AcquireImage' events
        acq = (AcquireImage, type(None))
        if not isinstance(e0.action, acq) or not isinstance(event.action, acq):
            return False

        new_chunk_len = len(self.event_batch) + 1

        # NOTE: these should be ordered from "fastest to check / most likely to fail",
        # to "slowest to check / most likely to pass"

        # If it's a new timepoint, and they have a different start time
        # we don't (yet) support sequencing.
        if (
            event.index.get("t") != e0.index.get("t")
            and event.min_start_time != e0.min_start_time
        ):
            return False

        # Exposure
        if event.exposure != e0.exposure:
            if new_chunk_len > self.max_lengths[Keyword.CoreCamera]:
                return False
            self.attribute_changes[Keyword.CoreCamera] = True

        # XY
        if event.x_pos != e0.x_pos or event.y_pos != e0.y_pos:
            if new_chunk_len > self.max_lengths[Keyword.CoreXYStage]:
                return False
            self.attribute_changes[Keyword.CoreXYStage] = True

        # Z
        if event.z_pos != e0.z_pos:
            if new_chunk_len > self.max_lengths[Keyword.CoreFocus]:
                return False
            self.attribute_changes[Keyword.CoreFocus] = True

        # SLM
        if event.slm_image != e0.slm_image:
            if new_chunk_len > self.max_lengths[Keyword.CoreSLM]:
                return False
            self.attribute_changes[Keyword.CoreSLM] = True

        # properties
        event_props = self._event_properties(event)
        all_props = event_props.keys() | self.first_event_props.keys()
        for dev_prop in all_props:
            new_val = event_props.get(dev_prop)
            old_val = self.first_event_props.get(dev_prop)
            if new_val != old_val:
                # if the property has changed, (or is missing in one dict)
                if new_chunk_len > self._get_property_max_length(dev_prop):
                    return False
                self.attribute_changes[dev_prop] = True

        return True

    def flush(self) -> MDAEvent | SequencedEvent | None:
        """Flush any remaining events in the buffer."""
        if not self.event_batch:
            return None
        result = self._create_sequenced_event()
        self._reset_tracking()
        return result

    def _create_sequenced_event(self) -> MDAEvent | SequencedEvent:
        """Convert self.event_batch into a SequencedEvent.

        If the batch contains only a single event, that event is returned directly.
        """
        if not self.event_batch:
            raise RuntimeError("Cannot flush an empty chunk")

        first_event = self.event_batch[0]

        if (num_events := len(self.event_batch)) == 1:
            return first_event

        exposures: list[float | None] = []
        x_positions: list[float | None] = []
        y_positions: list[float | None] = []
        z_positions: list[float | None] = []
        slm_images: list[Any] = []
        property_sequences: defaultdict[tuple[str, str], list[Any]] = defaultdict(list)
        static_props: list[tuple[str, str, Any]] = []

        # Single pass
        for e in self.event_batch:
            exposures.append(e.exposure)
            x_positions.append(e.x_pos)
            y_positions.append(e.y_pos)
            z_positions.append(e.z_pos)
            slm_images.append(e.slm_image)
            for dev_prop, val in self._event_properties(e).items():
                property_sequences[dev_prop].append(val)

        # remove any property sequences that are static
        for key, prop_seq in list(property_sequences.items()):
            if not self.attribute_changes.get(key):
                static_props.append((*key, prop_seq[0]))
                property_sequences.pop(key)
            elif len(prop_seq) != num_events:
                raise RuntimeError(
                    "Property sequence length mismatch. "
                    "Please report this with an example."
                )

        exp_changed = self.attribute_changes.get(Keyword.CoreCamera)
        xy_changed = self.attribute_changes.get(Keyword.CoreXYStage)
        z_changed = self.attribute_changes.get(Keyword.CoreFocus)
        slm_changed = self.attribute_changes.get(Keyword.CoreSLM)

        exp_seq = tuple(exposures) if exp_changed else ()
        x_seq = tuple(x_positions) if xy_changed else ()
        y_seq = tuple(y_positions) if xy_changed else ()
        z_seq = tuple(z_positions) if z_changed else ()
        slm_seq = tuple(slm_images) if slm_changed else ()

        return SequencedEvent(
            events=tuple(self.event_batch),
            exposure_sequence=exp_seq,
            x_sequence=x_seq,
            y_sequence=y_seq,
            z_sequence=z_seq,
            slm_sequence=slm_seq,
            property_sequences=property_sequences,
            properties=static_props,
            # all other "standard" MDAEvent fields are derived from the first event
            # the engine will use these values if the corresponding sequence is empty
            x_pos=first_event.x_pos,
            y_pos=first_event.y_pos,
            z_pos=first_event.z_pos,
            exposure=first_event.exposure,
            channel=first_event.channel,
        )

    # -------------- helper methods to query props & max lengths ----------------

    def _event_properties(self, event: MDAEvent) -> dict[tuple[str, str], Any]:
        """Return a dict of all property values for a given event."""
        props: dict[tuple[str, str], Any] = {}

        if (ch := event.channel) is not None:
            props.update(self._get_channel_properties(ch))
        if event.properties:
            for dev, prop, val in event.properties:
                props[(dev, prop)] = val
        return props

    def _get_channel_properties(self, ch: EventChannel) -> dict[tuple[str, str], Any]:
        """Get (and cache) property values for a given channel."""
        if ch not in self._channel_props:
            cfg = self.core.getConfigData(ch.group, ch.config, native=True)
            data: dict[tuple[str, str], Any] = {}
            for n in range(cfg.size()):
                s = cfg.getSetting(n)
                data[(s.getDeviceLabel(), s.getPropertyName())] = s.getPropertyValue()
            self._channel_props[ch] = data

        return self._channel_props[ch]

    def _get_property_max_length(self, dev_prop: tuple[str, str]) -> int:
        """Get (and cache) the max sequence length for a given property."""
        if dev_prop not in self._prop_lengths:
            max_length = 0
            with suppress(RuntimeError):
                dev, prop = dev_prop
                if self.core.isPropertySequenceable(dev, prop):
                    max_length = self.core.getPropertySequenceMaxLength(dev, prop)
            self._prop_lengths[dev_prop] = max_length
        return self._prop_lengths[dev_prop]


def _get_max_sequence_lengths(core: CMMCorePlus) -> dict[Keyword, int]:
    max_lengths: dict[Keyword, int] = {}
    for keyword, get_device, is_sequenceable, get_max_length in (
        (
            Keyword.CoreCamera,
            core.getCameraDevice,
            core.isExposureSequenceable,
            core.getExposureSequenceMaxLength,
        ),
        (
            Keyword.CoreFocus,
            core.getFocusDevice,
            core.isStageSequenceable,
            core.getStageSequenceMaxLength,
        ),
        (
            Keyword.CoreXYStage,
            core.getXYStageDevice,
            core.isXYStageSequenceable,
            core.getXYStageSequenceMaxLength,
        ),
        (
            Keyword.CoreSLM,
            core.getSLMDevice,
            lambda _device: True,  # there is no isSLMSequenceable method
            core.getSLMSequenceMaxLength,
        ),
    ):
        max_lengths[keyword] = 0
        with suppress(RuntimeError):
            if (device := get_device()) and is_sequenceable(device):
                max_lengths[keyword] = get_max_length(device)
    return max_lengths


def can_sequence_events(core: CMMCorePlus, e1: MDAEvent, e2: MDAEvent) -> bool:
    """Check whether two [`useq.MDAEvent`][] are sequenceable.

    !!! warning
        This function is deprecated and should not be used in new code. It is only
        retained for backwards compatibility.
    """
    # this is an old function that simply exists to return a value in the deprecated
    # core.canSequenceEvents method.  It is not used in the current implementation
    # and should not be used in new code.
    combiner = EventCombiner(core)
    combiner.feed_event(e1)
    return combiner.can_extend(e2)
