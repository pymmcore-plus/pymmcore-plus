from __future__ import annotations

from itertools import product
from typing import TYPE_CHECKING, Literal, Sequence, overload

from useq import MDAEvent

from pymmcore_plus.core._constants import DeviceType

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class SequencedEvent(MDAEvent):
    events: tuple[MDAEvent, ...]
    exposure_sequence: tuple[float, ...]
    x_sequence: tuple[float, ...]
    y_sequence: tuple[float, ...]
    z_sequence: tuple[float, ...]
    channels: tuple[str, ...]

    def property_sequences(self, core: CMMCorePlus) -> dict[tuple[str, str], list[str]]:
        prop_seqs: dict[tuple[str, str], list[str]] = {}
        if not self.events[0].channel:
            return prop_seqs
        for e in self.events:
            e_cfg = core.getConfigData(e.channel.group, e.channel.config)  # type: ignore # noqa
            for dev, prop, val in e_cfg:
                if core.isPropertySequenceable(dev, prop):
                    prop_seqs.setdefault((dev, prop), []).append(val)
        return prop_seqs

    @classmethod
    def create(cls, events: Sequence[MDAEvent]) -> SequencedEvent:
        """Create a new SequencedEvent from a sequence of events."""
        _events = tuple(events)
        if len(_events) <= 1:
            raise ValueError("Sequences must have at least two events.")

        attrs = ("z_pos", "x_pos", "y_pos", "exposure", "channel")
        dd: dict[str, list] = {attr: [] for attr in attrs}

        for event, attr in product(_events, attrs):
            if (val := getattr(event, attr)) is not None:
                dd[attr].append(val)

        return cls(
            events=_events,
            exposure_sequence=tuple(dd["exposure"]),
            x_sequence=tuple(dd["x_pos"]),
            y_sequence=tuple(dd["y_pos"]),
            z_sequence=tuple(dd["z_pos"]),
            channels=tuple(c.config for c in dd["channel"]),
            **_events[0].dict(),  # use the first event as the "base" event
        )

    @property
    def is_exposure_sequenced(self) -> bool:
        return len(set(self.exposure_sequence)) > 1

    @property
    def is_xy_sequenced(self) -> bool:
        return len(set(self.x_sequence)) > 1 and len(set(self.y_sequence)) > 1

    @property
    def is_z_sequenced(self) -> bool:
        return len(set(self.z_sequence)) > 1

    @property
    def is_channel_sequenced(self) -> bool:
        return len(set(self.channels)) > 1

    @property
    def channel_info(self) -> tuple[str, str] | None:
        """Return channel group & config, or None."""
        e0 = self.events[0]
        return (e0.channel.group, e0.channel.config) if e0.channel else None


def get_all_sequenceable(core: CMMCorePlus) -> dict[tuple[str | DeviceType, str], int]:
    """Return all sequenceable devices in `core`.

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
) -> bool:
    ...


@overload
def can_sequence_events(
    core: CMMCorePlus,
    e1: MDAEvent,
    e2: MDAEvent,
    cur_length: int = ...,
    *,
    return_reason: Literal[True],
) -> tuple[bool, str]:
    ...


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

    # channel
    def _r(reason: str) -> tuple[bool, str] | bool:
        return (False, reason) if return_reason else False

    if e1.channel and e2.channel and (e1.channel != e2.channel):
        cfg = core.getConfigData(e1.channel.group, e1.channel.config)
        for dev, prop, _ in cfg:
            # note: we don't need _ here, so can perhaps speed up with native=True
            if not core.isPropertySequenceable(dev, prop):
                return _r(f"'{dev}-{prop}' is not sequenceable")
            max_len = core.getPropertySequenceMaxLength(dev, prop)
            if cur_length >= max_len:
                return _r(f"'{dev}-{prop}' {max_len=} < {cur_length=}")

    # Z
    if e1.z_pos and e2.z_pos and (e1.z_pos != e2.z_pos):
        focus_dev = core.getFocusDevice()
        if not core.isStageSequenceable(focus_dev):
            return _r(f"Focus device {focus_dev!r} is not sequenceable")
        max_len = core.getStageSequenceMaxLength(focus_dev)
        if cur_length >= max_len:
            return _r(f"Focus device {focus_dev!r} {max_len=} < {cur_length=}")

    # XY
    if (e1.x_pos and e2.x_pos and (e1.x_pos != e2.x_pos)) or (
        e1.y_pos and e2.y_pos and (e1.y_pos != e2.y_pos)
    ):
        stage = core.getXYStageDevice()
        if not core.isXYStageSequenceable(stage):
            return _r(f"XYStage {stage!r} is not sequenceable")
        max_len = core.getXYStageSequenceMaxLength(stage)
        if cur_length >= max_len:
            return _r(f"XYStage {stage!r} {max_len=} < {cur_length=}")

    # camera
    cam_dev = core.getCameraDevice()
    if not core.isExposureSequenceable(cam_dev):
        if e1.exposure != e2.exposure:
            return _r(f"Camera {cam_dev!r} is not exposure-sequenceable")
    elif cur_length >= core.getExposureSequenceMaxLength(cam_dev):
        return _r(f"Camera {cam_dev!r} {max_len=} < {cur_length=}")

    # time
    # TODO: use better axis keys when they are available
    if (
        e1.index.get("t") != e2.index.get("t")
        and e1.min_start_time != e2.min_start_time
    ):
        pause = (e2.min_start_time or 0) - (e1.min_start_time or 0)
        return _r(f"Must pause at least {pause} s between events.")

    # misc additional properties
    if e1.properties and e2.properties:
        for dev, prop, value1 in e1.properties:
            for dev2, prop2, value2 in e2.properties:
                if dev == dev2 and prop == prop2 and value1 != value2:
                    if not core.isPropertySequenceable(dev, prop):
                        return _r(f"'{dev}-{prop}' is not sequenceable")
                    if cur_length >= core.getPropertySequenceMaxLength(dev, prop):
                        return _r(f"'{dev}-{prop}' {max_len=} < {cur_length=}")

    return (True, "") if return_reason else True
