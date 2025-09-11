from enum import Enum
from typing import ClassVar, Protocol, runtime_checkable

from pymmcore_plus.core.events._protocol import PSignal


class RunStatus(str, Enum):
    """Enumeration of the possible states of the MDA runner."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELED = "canceled"
    ERROR = "error"
    COMPLETED = "completed"

    def __str__(self) -> str:
        return str(self.value)


@runtime_checkable
class PMDASignaler(Protocol):
    """Declares the protocol for all signals that will be emitted from [`pymmcore_plus.mda.MDARunner`][]."""  # noqa: E501

    sequenceStarted: ClassVar[PSignal]
    """Emits `(sequence: MDASequence, metadata: dict)` when an acquisition sequence is started.

    For the default [`MDAEngine`][pymmcore_plus.mda.MDAEngine], the metadata `dict` will
    be of type [`SummaryMetaV1`][pymmcore_plus.metadata.schema.SummaryMetaV1].
    """  # noqa: E501
    sequencePauseToggled: ClassVar[PSignal]
    """Emits `(paused: bool)` when an acquisition sequence is paused or unpaused."""
    sequenceCanceled: ClassVar[PSignal]
    """Emits `(sequence: MDASequence)` when an acquisition sequence is canceled."""
    sequenceFinished: ClassVar[PSignal]
    """Emits `(sequence: MDASequence, status: RunStatus, summary_meta: Mapping, frame_metas: tuple[Mapping])` when an acquisition sequence is finished.

    In practice summary_meta will often be of type
    [`SummaryMetaV1`][pymmcore_plus.metadata.schema.SummaryMetaV1] and frame_metas will
    often be a tuple of [`FrameMetaV1`][pymmcore_plus.metadata.schema.FrameMetaV1]
    objects. But that is only true if the [`MDAEngine`][pymmcore_plus.mda.MDAEngine]
    used in the acquisition produces metadata of those types.
    """  # noqa: E501
    frameReady: ClassVar[PSignal]
    """Emits `(img: np.ndarray, event: MDAEvent, metadata: dict)` after an image is acquired during an acquisition sequence.

    For the default [`MDAEngine`][pymmcore_plus.mda.MDAEngine], the metadata `dict` will
    be of type [`FrameMetaV1`][pymmcore_plus.metadata.schema.FrameMetaV1].
    """  # noqa: E501
    awaitingEvent: ClassVar[PSignal]
    """Emits `(event: MDAEvent, remaining_sec: float)` when the runner is waiting to start an event.

    Note: Not all events in a sequence will emit this signal. This will only be emitted
    if the wait time is non-zero.
    """  # noqa: E501
    eventStarted: ClassVar[PSignal]
    """Emits `(event: MDAEvent)` immediately before event setup and execution."""
