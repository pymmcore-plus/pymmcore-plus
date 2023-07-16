from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

from useq import MDAEvent

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


@dataclass(frozen=True)
class SequencedEvent:
    events: tuple[MDAEvent, ...] = field(repr=False)
    exposure_sequence: tuple[float, ...]
    x_sequence: tuple[float, ...]
    y_sequence: tuple[float, ...]
    z_sequence: tuple[float, ...]
    channels: tuple[str, ...]

    @property
    def min_start_time(self) -> float | None:
        """Return the minimum start time of all events, or None."""
        return self.events[0].min_start_time

    @classmethod
    def create(cls, events: Iterable[MDAEvent]) -> SequencedEvent:
        """Create a new SequencedEvent from a sequence of events."""
        z_positions: list[float] = []
        x_positions: list[float] = []
        y_positions: list[float] = []
        exposures: list[float] = []
        channels: list[str] = []
        _events = tuple(events)
        for event in _events:
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

        return cls(
            events=_events,
            exposure_sequence=tuple(exposures),
            x_sequence=tuple(x_positions),
            y_sequence=tuple(y_positions),
            z_sequence=tuple(z_positions),
            channels=tuple(channels),
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


def can_sequence_events(
    core: CMMCorePlus, e1: MDAEvent, e2: MDAEvent, cur_length: int = -1
) -> tuple[bool, str]:
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

    Returns
    -------
    tuple[bool, str]
        A tuple of a boolean indicating whether the events can be sequenced and a
        string describing the reason for failure if the events cannot be sequenced.

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
    if e1.channel and e2.channel and (e1.channel != e2.channel):
        cfg = core.getConfigData(e1.channel.group, e1.channel.config)
        for dev, prop, _ in cfg:
            # note: we don't need _ here, so can perhaps speed up with native=True
            if not core.isPropertySequenceable(dev, prop):
                return False, f"'{dev}-{prop}' is not sequenceable"
            max_len = core.getPropertySequenceMaxLength(dev, prop)
            if cur_length >= max_len:
                return False, f"'{dev}-{prop}' {max_len=} < {cur_length=}"

    # Z
    if e1.z_pos and e2.z_pos and (e1.z_pos != e2.z_pos):
        focus_dev = core.getFocusDevice()
        if not core.isStageSequenceable(focus_dev):
            return False, f"Focus device {focus_dev!r} is not sequenceable"
        max_len = core.getStageSequenceMaxLength(focus_dev)
        if cur_length >= max_len:
            return False, f"Focus device {focus_dev!r} {max_len=} < {cur_length=}"

    # XY
    if (e1.x_pos and e2.x_pos and (e1.x_pos != e2.x_pos)) or (
        e1.y_pos and e2.y_pos and (e1.y_pos != e2.y_pos)
    ):
        stage = core.getXYStageDevice()
        if not core.isXYStageSequenceable(stage):
            return False, f"XYStage {stage!r} is not sequenceable"
        max_len = core.getXYStageSequenceMaxLength(stage)
        if cur_length >= max_len:
            return False, f"XYStage {stage!r} {max_len=} < {cur_length=}"

    # camera
    cam_dev = core.getCameraDevice()
    if not core.isExposureSequenceable(cam_dev):
        if e1.exposure != e2.exposure:
            return False, f"Camera {cam_dev!r} is not exposure-sequenceable"
    elif cur_length >= core.getExposureSequenceMaxLength(cam_dev):
        return False, f"Camera {cam_dev!r} {max_len=} < {cur_length=}"

    # time
    # TODO: use better axis keys when they are available
    if (
        e1.index.get("t") != e2.index.get("t")
        and e1.min_start_time != e2.min_start_time
    ):
        pause = (e2.min_start_time or 0) - (e1.min_start_time or 0)
        return False, f"Must pause at least {pause} s between events."

    # misc additional properties
    if e1.properties and e2.properties:
        for dev, prop, value1 in e1.properties:
            for dev2, prop2, value2 in e2.properties:
                if dev == dev2 and prop == prop2 and value1 != value2:
                    if not core.isPropertySequenceable(dev, prop):
                        return False, f"'{dev}-{prop}' is not sequenceable"
                    if cur_length >= core.getPropertySequenceMaxLength(dev, prop):
                        return False, f"'{dev}-{prop}' {max_len=} < {cur_length=}"

    return True, ""
