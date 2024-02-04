from typing import Protocol, runtime_checkable

from pymmcore_plus.core.events._protocol import PSignal


@runtime_checkable
class PMDASignaler(Protocol):
    """Declares the protocol for all signals that will be emitted from [`pymmcore_plus.mda.MDARunner`][]."""  # noqa: E501

    sequenceStarted: PSignal
    """Emits `(sequence: MDASequence, metadata: dict)` when an acquisition sequence is started."""  # noqa: E501
    sequencePauseToggled: PSignal
    """Emits `(paused: bool)` when an acquisition sequence is paused or unpaused."""
    sequenceCanceled: PSignal
    """Emits `(sequence: MDASequence)` when an acquisition sequence is canceled."""
    sequenceFinished: PSignal
    """Emits `(sequence: MDASequence)` when an acquisition sequence is finished."""
    frameReady: PSignal
    """Emits `(img: np.ndarray, event: MDAEvent, metadata: dict)` after an image is acquired during an acquisition sequence."""  # noqa: E501
    awaitingEvent: PSignal
    """Emits `(event: MDAEvent, remaining_sec: float)` when the runner is waiting to start an event.

    Note: Not all events in a sequence will emit this signal. This will only be emitted
    if the wait time is non-zero.
    """  # noqa: E501
    eventStarted: PSignal
    """Emits `(event: MDAEvent)` immediately before event setup and execution."""
