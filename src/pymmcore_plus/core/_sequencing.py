from __future__ import annotations

from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, Self, TypeVar, cast

from pydantic import Field, model_validator
from useq import AcquireImage, MDAEvent

from pymmcore_plus.core._constants import DeviceType, Keyword

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from pymmcore_plus import CMMCorePlus


T = TypeVar("T")


class SequencedEvent(MDAEvent):
    """Subclass of MDAEvent that represents a sequence of triggered events."""

    events: tuple[MDAEvent, ...] = Field(repr=False)

    exposure_sequence: tuple[float, ...] = Field(default_factory=tuple)
    x_sequence: tuple[float, ...] = Field(default_factory=tuple)
    y_sequence: tuple[float, ...] = Field(default_factory=tuple)
    z_sequence: tuple[float, ...] = Field(default_factory=tuple)
    slm_sequence: tuple[bytes, ...] = Field(default_factory=tuple)
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


@dataclass
class SequenceItem(Generic[T]):
    """A single sequence of values for a given property.

    This structure is used by `SequenceData` to keep track of the values for each
    property that may need to be sequenced, (whether it be a core device or a device
    property).

    Parameters
    ----------
    max_length : int
        The maximum allowed length of the sequence.  Usually determined by the core's
        `get*SequenceMaxLength` method.  A max_length of 0 indicates that the property
        is not sequenceable.
    sequence : list[T], optional
        The sequence of accumulated values, by default an empty list.
    sequence_set : set[T], optional
        A set of unique values in the sequence, by default an empty set.  This is
        maintained in parallel with the `sequence` list to allow for quick lookups
        of unique values.
    """

    max_length: int
    sequence: list[T] = field(default_factory=list)
    sequence_set: set[T] = field(default_factory=set)

    def __len__(self) -> int:
        """Return the length of the sequence."""
        return len(self.sequence)

    def has_multiple_values(self) -> int:
        """Return True if the sequence has more than one unique value."""
        return len(self.sequence_set) > 1

    def append(self, value: Any) -> None:
        """Append a value to the sequence."""
        self.sequence.append(value)
        self.sequence_set.add(value)

    def can_append(self, value: Any) -> bool:
        """Return True if `value` can be appended to the sequence."""
        # if adding the new value would make the sequence non-unique
        # then we can only append if the sequence is not already at max length
        if len(self.sequence_set | {value}) > 1:
            return len(self) < self.max_length

        # otherwise, we can always append
        return True


@dataclass
class SequenceData:
    """Temporary data structure for constructing a SequencedEvent.

    This object is used within the `iter_sequenced_events` function to accumulate
    events and determine when a sequence has been completed.  It then converts the
    accumulated data into a `SequencedEvent` object using the `to_mda_event` method.
    """

    core: CMMCorePlus
    events: list[MDAEvent] = field(default_factory=list)
    items: dict[str | tuple[str, str], SequenceItem] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # initialize items dict with max sequenceable length of all core devices
        for keyword, get_device, is_sequenceable, get_max_length in (
            (
                Keyword.CoreCamera,
                self.core.getCameraDevice,
                self.core.isExposureSequenceable,
                self.core.getExposureSequenceMaxLength,
            ),
            (
                Keyword.CoreFocus,
                self.core.getFocusDevice,
                self.core.isStageSequenceable,
                self.core.getStageSequenceMaxLength,
            ),
            (
                Keyword.CoreXYStage,
                self.core.getXYStageDevice,
                self.core.isXYStageSequenceable,
                self.core.getXYStageSequenceMaxLength,
            ),
            (
                Keyword.CoreSLM,
                self.core.getSLMDevice,
                lambda d: True,
                self.core.getSLMSequenceMaxLength,
            ),
        ):
            # if the keyword is already present, we can skip and save time.
            if keyword not in self.items:
                max_length = 0
                with suppress(RuntimeError):
                    if (device := get_device()) and is_sequenceable(device):
                        max_length = get_max_length(device)
                self.items[keyword] = SequenceItem(max_length)

    def try_add_event(self, event: MDAEvent) -> bool:
        """Return True if the event was successfully added to the sequence."""
        # TODO: consider returning a string instead of False to indicate why the event
        # could not be added to the sequence.

        # cannot add pre-existing SequencedEvents to the sequence
        if isinstance(event, SequencedEvent):
            return False
        # cannot sequence non-'AcquireImage' events
        if not isinstance(event.action, (AcquireImage, type(None))):
            return False

        event_vals = self._get_event_values(event)
        for key, value in event_vals:
            if key not in self.items:
                # we've never seen this property before;
                # check with the core to see if it's sequenceable and get the max length
                dev, prop = cast("tuple[str, str]", key)
                max_len = (
                    self.core.getPropertySequenceMaxLength(dev, prop)
                    if self.core.isPropertySequenceable(dev, prop)
                    else 0
                )
                self.items[key] = SequenceItem(max_len)
            # if we can't append the value to this particular axis,
            # then we've reached the end of the sequence
            if not self.items[key].can_append(value):
                return False

        # ATOMIC UPDATE
        # if we've made it this far, we can actually add all of the values
        for key, value in event_vals:
            self.items[key].append(value)
        self.events.append(event)

        return True

    def _get_event_values(
        self, event: MDAEvent
    ) -> Sequence[tuple[str | tuple[str, str], Any]]:
        """Extract the values from the event that should be checked for sequencing."""
        vals: list[tuple[str | tuple[str, str], Any]] = [
            (Keyword.CoreCamera, event.exposure),
            (Keyword.CoreFocus, event.z_pos),
            (Keyword.CoreXYStage, (event.x_pos, event.y_pos)),
        ]
        if ch := event.channel:
            for dev, prop, val in self.core.getConfigData(ch.group, ch.config):
                vals.append(((dev, prop), val))
        if event.properties:
            for dev, prop, val in event.properties:
                vals.append(((dev, prop), val))
        return vals

    def to_mda_event(self) -> SequencedEvent | MDAEvent:
        """Convert the collected data into a SequencedEvent or MDAEvent."""
        if not self.events:  # pragma: no cover
            raise ValueError("SequenceData must have at least one event to convert.")

        # if we only have one event, there's no need to merge into a SequencedEvent
        first_event = self.events[0]
        if len(self.events) == 1:
            return first_event

        # now we need to merge the data into a SequencedEvent
        # in each case, if there is a single value, that axis does not need to be
        # sequenced at all. We just include the static value in the regular MDAEvent
        # field (see bottom half of SequencedEvent constructor).
        # Otherwise we include the sequence extracted from the SequenceItem.

        # xy stage sequence
        items = self.items.copy()
        xy_item: SequenceItem[tuple[float | None, float | None]]
        xy_item = items.pop(Keyword.CoreXYStage)
        x_seq, y_seq = (
            zip(*xy_item.sequence) if xy_item.has_multiple_values() else ((), ())
        )

        # exposure sequence
        cam_item: SequenceItem[float]
        cam_item = items.pop(Keyword.CoreCamera)
        exp_seq = tuple(cam_item.sequence) if cam_item.has_multiple_values() else ()

        # focus sequence
        z_item = items.pop(Keyword.CoreFocus)
        z_seq = tuple(z_item.sequence) if z_item.has_multiple_values() else ()

        # SLM not yet implemented.  TODO: This needs to be added to useq.MDAEvent first.
        _slm_item = items.pop(Keyword.CoreSLM, None)

        # all other property sequences
        sequenced_props = {}
        static_props = []
        for k, v in items.items():
            if v.has_multiple_values():
                sequenced_props[k] = v.sequence
            else:
                static_props.append((*k, v.sequence[0]))

        return SequencedEvent(
            events=tuple(self.events),
            exposure_sequence=exp_seq,
            x_sequence=x_seq,
            y_sequence=y_seq,
            z_sequence=z_seq,
            property_sequences=sequenced_props,
            properties=static_props,
            # all other "standard" MDAEvent fields are derived from the first event
            # the engine will use these values if the corresponding sequence is empty
            x_pos=first_event.x_pos,
            y_pos=first_event.y_pos,
            z_pos=first_event.z_pos,
            exposure=first_event.exposure,
            channel=first_event.channel,
        )

    def clear(self) -> None:
        """Clear all sequences.

        This resets the data structure to prepare for the next sequence, without losing
        max_length information for each property.
        """
        self.events.clear()
        for item in self.items.values():
            item.sequence.clear()
            item.sequence_set.clear()


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
        the engine to check `isisntance(event, SequencedEvent)` in order to handle
        SequencedEvents differently.
    """
    seq_data = SequenceData(core)

    for event in events:
        # if try_add_event returns True, the event was successfully added to the seq.
        # if not, we've reached the end of the sequence, and we need to yield the
        # current sequence and start a new one.
        if seq_data.try_add_event(event):
            continue

        if seq_data.events:
            # if we've accumulated any events, merge and yield them
            yield seq_data.to_mda_event()
            seq_data.clear()

        # add the current event to a new sequence...
        # if it can't be added even as the first event, then we'll just yield it
        if not seq_data.try_add_event(event):
            yield event

    # yield the last event if there are any
    if len(seq_data.events):
        yield seq_data.to_mda_event()


def get_all_sequenceable(core: CMMCorePlus) -> dict[tuple[str | DeviceType, str], int]:
    """Return all sequenceable devices in `core`.

    This is just a convenience function to help determine which devices can be
    sequenced on a given configuration.

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


def _can_sequence_events(core: CMMCorePlus, e1: MDAEvent, e2: MDAEvent) -> bool:
    """Check whether two [`useq.MDAEvent`][] are sequenceable."""
    # this is an old function that simply exists to return a value in the deprecated
    # core.canSequenceEvents method.  It is not used in the current implementation
    # and should not be used in new code.
    seq_data = SequenceData(core)
    return seq_data.try_add_event(e1) and seq_data.try_add_event(e2)
