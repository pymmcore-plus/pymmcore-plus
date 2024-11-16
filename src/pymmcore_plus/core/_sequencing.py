from __future__ import annotations

from contextlib import suppress
from itertools import chain, product
from typing import TYPE_CHECKING, Literal, Self, TypeAlias, overload

from pydantic import model_validator
from useq import AcquireImage, MDAEvent

from pymmcore_plus.core._constants import DeviceType, Keyword

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from pymmcore_plus import CMMCorePlus

    MaxLengths: TypeAlias = dict[str | tuple[str, str], int]


class SequencedEvent(MDAEvent):
    """Subclass of MDAEvent that represents a sequence of triggered events.

    Prefer instantiating this class via the `create` classmethod, which will
    calculate sequences for x, y, z, and exposure based on an a sequence of events.
    """

    events: tuple[MDAEvent, ...]
    exposure_sequence: tuple[float, ...]
    x_sequence: tuple[float, ...]
    y_sequence: tuple[float, ...]
    z_sequence: tuple[float, ...]
    property_sequences: dict[tuple[str, str], list[str]]

    @model_validator(mode="after")
    def _check_sequence(self) -> Self:
        if len(self.x_sequence) != len(self.y_sequence):
            raise ValueError("X and Y sequences must be the same length")
        return self

    # # technically this is more like a field, but it requires a core instance
    # # to getConfigData for channels, so we leave it as a method.
    # def property_sequences(self, core: CMMCorePlus) -> dict[tuple[str, str], list[str]]:
    #     """Return a dict of all sequenceable properties and their sequences.

    #     Returns
    #     -------
    #     dict[tuple[str, str], list[str]]
    #         mapping of (device_name, prop_name) -> sequence of values
    #     """
    #     prop_seqs: dict[tuple[str, str], list[str]] = {}
    #     if not self.events[0].channel:
    #         return {}

    #     # NOTE: we already should have checked that all of these properties were
    #     # Sequenceable in can_sequence_events, so we don't check again here.
    #     for e in self.events:
    #         if e.channel is not None:
    #             e_cfg = core.getConfigData(e.channel.group, e.channel.config)
    #             for dev, prop, val in e_cfg:
    #                 prop_seqs.setdefault((dev, prop), []).append(val)
    #         if e.properties:
    #             for dev, prop, val in e.properties:
    #                 prop_seqs.setdefault((dev, prop), []).append(val)

    #     # filter out any sequences that are all the same value
    #     return {k: v for k, v in prop_seqs.items() if len(set(v)) > 1}

    @classmethod
    def create(cls, events: Sequence[MDAEvent]) -> SequencedEvent:
        """Create a SequencedEvent from a sequence of events.

        This pre-calculates sequences of length > 1 for x, y, z positions, and exposure.
        Channel configs and other sequenceable properties are determined by the
        `property_sequences` method, which requires access to a core instance.
        """
        _events = tuple(events)
        if len(_events) <= 1:
            raise ValueError("Sequences must have at least two events.")

        data: dict[str, list] = {a: [] for a in ("z_pos", "x_pos", "y_pos", "exposure")}
        for event, attr in product(_events, list(data)):
            # do we need to check if not None?
            # the only problem might occur if some are None and some are not
            data[attr].append(getattr(event, attr))

        x_seq = data["x_pos"] if len(set(data["x_pos"])) > 1 else ()
        y_seq = data["y_pos"] if len(set(data["y_pos"])) > 1 else ()

        props = {}

        e0 = _events[0]
        return cls(
            events=_events,
            exposure_sequence=(
                data["exposure"] if len(set(data["exposure"])) > 1 else ()
            ),
            x_sequence=x_seq,
            y_sequence=y_seq,
            z_sequence=data["z_pos"] if len(set(data["z_pos"])) > 1 else (),
            property_sequences=props,
            # use the first event to provide all other values like min_start_time, etc.
            **(e0.model_dump() if hasattr(e0, "model_dump") else e0.dict()),
        )


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


@overload
def can_sequence_events(
    core: CMMCorePlus,
    e1: MDAEvent,
    e2: MDAEvent,
    cur_length: int = ...,
    *,
    return_reason: Literal[False] = ...,
) -> bool: ...


@overload
def can_sequence_events(
    core: CMMCorePlus,
    e1: MDAEvent,
    e2: MDAEvent,
    cur_length: int = ...,
    *,
    return_reason: Literal[True],
) -> tuple[bool, str]: ...


def can_sequence_events(
    core: CMMCorePlus,
    e1: MDAEvent,
    e2: MDAEvent,
    cur_length: int = -1,
    *,
    return_reason: bool = False,
) -> bool | tuple[bool, str]:
    """Check whether two [`useq.MDAEvent`][] are sequenceable.

    Micro-manager calls hardware triggering "sequencing".  Two events can be
    sequenced if *all* device properties that are changing between the first and
    second event support sequencing.

    If `cur_length` is provided, it is used to determine if the sequence is
    "full" (i.e. the sequence is already at the maximum length) as determined by
    the `...SequenceMaxLength()` method corresponding to the device property.

    See: <https://micro-manager.org/Hardware-based_Synchronization_in_Micro-Manager>

    Parameters
    ----------
    core : CMMCorePlus
        The core instance.
    e1 : MDAEvent
        The first event.
    e2 : MDAEvent
        The second event.
    cur_length : int
        The current length of the sequence.  Used when checking
        `.get<...>SequenceMaxLength` for a given property. If the current length
        is greater than the max length, the events cannot be sequenced. By default
        -1, which means the current length is not checked.
    return_reason : bool
        If True, return a tuple of (bool, str) where the str is a reason for failure.
        Otherwise just return a bool.

    Returns
    -------
    bool | tuple[bool, str]
        If return_reason is True, return a tuple of a boolean indicating whether the
        events can be sequenced and a string describing the reason for failure if the
        events cannot be sequenced.  Otherwise just return a boolean indicating
        whether the events can be sequenced.

    Examples
    --------
    !!! note

        The results here will depend on the current state of the core and devices.

    ```python
    >>> from useq import MDAEvent
    >>> core = CMMCorePlus.instance()
    >>> core.loadSystemConfiguration()
    >>> can_sequence_events(core, MDAEvent(), MDAEvent())
    (True, "")
    >>> can_sequence_events(core, MDAEvent(x_pos=1), MDAEvent(x_pos=2))
    (False, "Stage 'XY' is not sequenceable")
    >>> can_sequence_events(
    ...     core,
    ...     MDAEvent(channel={'config': 'DAPI'}),
    ...     MDAEvent(channel={'config': 'FITC'})
    ... )
    (False, "'Dichroic-Label' is not sequenceable")
    ```
    """

    def _nope(reason: str) -> tuple[bool, str] | bool:
        return (False, reason) if return_reason else False

    # Action
    if not isinstance(e1.action, (AcquireImage, type(None))) or not isinstance(
        e2.action, (AcquireImage, type(None))
    ):
        return _nope("Cannot sequence non-'AcquireImage' events.")

    # channel
    if e1.channel and e1.channel != e2.channel:
        if not e2.channel or e1.channel.group != e2.channel.group:
            e2_channel_group = getattr(e2.channel, "group", None)
            return _nope(
                "Cannot sequence across config groups: "
                f"{e1.channel.group=}, {e2_channel_group=}"
            )
        cfg = core.getConfigData(e1.channel.group, e1.channel.config)
        for dev, prop, _ in cfg:
            # note: we don't need _ here, so can perhaps speed up with native=True
            if not core.isPropertySequenceable(dev, prop):
                return _nope(f"'{dev}-{prop}' is not sequenceable")
            max_len = core.getPropertySequenceMaxLength(dev, prop)
            if cur_length >= max_len:  # pragma: no cover
                return _nope(f"'{dev}-{prop}' {max_len=} < {cur_length=}")

    # Z
    if e1.z_pos != e2.z_pos:
        focus_dev = core.getFocusDevice()
        if not core.isStageSequenceable(focus_dev):
            return _nope(f"Focus device {focus_dev!r} is not sequenceable")
        max_len = core.getStageSequenceMaxLength(focus_dev)
        if cur_length >= max_len:  # pragma: no cover
            return _nope(f"Focus device {focus_dev!r} {max_len=} < {cur_length=}")

    # XY
    if e1.x_pos != e2.x_pos or e1.y_pos != e2.y_pos:
        stage = core.getXYStageDevice()
        if not core.isXYStageSequenceable(stage):
            return _nope(f"XYStage {stage!r} is not sequenceable")
        max_len = core.getXYStageSequenceMaxLength(stage)
        if cur_length >= max_len:  # pragma: no cover
            return _nope(f"XYStage {stage!r} {max_len=} < {cur_length=}")

    # camera
    cam_dev = core.getCameraDevice()
    if not core.isExposureSequenceable(cam_dev):
        if e1.exposure != e2.exposure:
            return _nope(f"Camera {cam_dev!r} is not exposure-sequenceable")
    elif cur_length >= core.getExposureSequenceMaxLength(cam_dev):  # pragma: no cover
        return _nope(f"Camera {cam_dev!r} {max_len=} < {cur_length=}")

    # time
    # TODO: use better axis keys when they are available
    if (
        e1.index.get("t") != e2.index.get("t")
        and e1.min_start_time != e2.min_start_time
    ):
        pause = (e2.min_start_time or 0) - (e1.min_start_time or 0)
        return _nope(f"Must pause at least {pause} s between events.")

    # misc additional properties
    if e1.properties and e2.properties:
        for dev, prop, value1 in e1.properties:
            for dev2, prop2, value2 in e2.properties:
                if dev == dev2 and prop == prop2 and value1 != value2:
                    if not core.isPropertySequenceable(dev, prop):
                        return _nope(f"'{dev}-{prop}' is not sequenceable")
                    if cur_length >= core.getPropertySequenceMaxLength(dev, prop):
                        return _nope(f"'{dev}-{prop}' {max_len=} < {cur_length=}")

    return (True, "") if return_reason else True


def iter_maybe_sequenced_events(
    events: Iterable[MDAEvent], mmc: CMMCorePlus
) -> Iterable[MDAEvent | SequencedEvent]:
    seq: list[MDAEvent] = []
    max_lengths = _max_core_dev_seq_lengths(mmc)

    for event in events:
        # if the sequence is empty or the current event can be sequenced with the
        # previous event, add it to the sequence
        if not seq or _can_sequence_events(
            mmc, seq[-1], event, len(seq), max_lengths=max_lengths
        ):
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


SNAP_ACTION = (AcquireImage, type(None))


def _can_sequence_events(
    core: CMMCorePlus,
    e1: MDAEvent,
    e2: MDAEvent,
    cur_length: int = -1,
    *,
    max_lengths: MaxLengths,
) -> tuple | None:
    # Action
    if not isinstance(e1.action, SNAP_ACTION) or not isinstance(e2.action, SNAP_ACTION):
        return None

    # properties
    for key in (prop_diff := _prop_diff(e1, e2, core)):
        dev, prop = key
        if key not in max_lengths:
            # this is an unseen property, check if it's sequenceable
            if not core.isPropertySequenceable(dev, prop):
                return None
            # NOTE: mutating max_lengths here to avoid rechecking in future loops
            max_lengths[key] = core.getPropertySequenceMaxLength(dev, prop)
        if cur_length >= max_lengths[key]:  # pragma: no cover
            return None

    # camera
    if (max_len := max_lengths[Keyword.CoreCamera]) == 0:
        if e1.exposure != e2.exposure:
            return None
    elif cur_length >= max_len:  # pragma: no cover
        return None

    # Z
    if e1.z_pos != e2.z_pos:
        if (max_len := max_lengths[Keyword.CoreFocus]) == 0:
            return None
        if cur_length >= max_len:  # pragma: no cover
            return None

    # XY
    if e1.x_pos != e2.x_pos or e1.y_pos != e2.y_pos:
        if (max_len := max_lengths[Keyword.CoreXYStage]) == 0:
            return None
        if cur_length >= max_len:  # pragma: no cover
            return None

    # time
    # TODO: use better axis keys when they are available
    if (
        e1.index.get("t") != e2.index.get("t")
        and e1.min_start_time != e2.min_start_time
    ):
        return None

    return e1, e2, prop_diff


def _prop_diff(
    e1: MDAEvent, e2: MDAEvent, core: CMMCorePlus
) -> dict[tuple[str, str], tuple[str | None, str | None]]:
    """Return the differences between two configurations."""
    cfg1 = (
        core.getConfigData(e1.channel.group, e1.channel.config)
        if e1.channel and e1.channel.group
        else ()
    )
    cfg2 = (
        core.getConfigData(e2.channel.group, e2.channel.config)
        if e2.channel and e2.channel.group
        else ()
    )
    props_1 = {(dev, prop): v for dev, prop, v in chain(cfg1, e1.properties or ())}
    props_2 = {(dev, prop): v for dev, prop, v in chain(cfg2, e2.properties or ())}

    # Collect all unique keys from both sets
    all_keys = set(props_1.keys()).union(props_2.keys())

    # Find changes
    changes: dict[tuple[str, str], tuple[str | None, str | None]] = {}
    for key in all_keys:
        value_a = props_1.get(key)
        value_b = props_2.get(key)
        if value_a != value_b:
            changes[key] = (value_a, value_b)

    return changes


def _max_core_dev_seq_lengths(core: CMMCorePlus) -> MaxLengths:
    """Return the max sequence lengths for all core devices.

    Returns
    -------
    dict[str, int]
        mapping of device name -> max sequence length

    Examples
    --------
    ```python
    >>> from pymmcore_plus import CMMCorePlus
    >>> core = CMMCorePlus.instance()
    >>> _max_core_dev_seq_lengths(core)
    {
        <Keyword.CoreCamera: 'Camera'>: 0,
        <Keyword.CoreFocus: 'Focus'>: 0,
        <Keyword.CoreXYStage: 'XYStage'>: 0,
        <Keyword.CoreSLM: 'SLM'>: 0}
    }
    ```
    """
    max_lengths: MaxLengths = {
        Keyword.CoreCamera: 0,
        Keyword.CoreFocus: 0,
        Keyword.CoreXYStage: 0,
        Keyword.CoreSLM: 0,
    }
    with suppress(RuntimeError):
        if (d := core.getCameraDevice()) and core.isExposureSequenceable(d):
            max_lengths[Keyword.CoreCamera] = core.getExposureSequenceMaxLength(d)
    with suppress(RuntimeError):
        if (d := core.getFocusDevice()) and core.isStageSequenceable(d):
            max_lengths[Keyword.CoreFocus] = core.getStageSequenceMaxLength(d)
    with suppress(RuntimeError):
        if (d := core.getXYStageDevice()) and core.isXYStageSequenceable(d):
            max_lengths[Keyword.CoreXYStage] = core.getXYStageSequenceMaxLength(d)
    with suppress(RuntimeError):
        max_lengths[Keyword.CoreSLM] = core.getSLMSequenceMaxLength(core.getSLMDevice())

    return max_lengths
