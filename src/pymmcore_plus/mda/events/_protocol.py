from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class PSignalInstance(Protocol):
    def connect(self, slot: Callable, **kwargs: Any) -> Any:
        ...

    def disconnect(self, slot: Callable, **kwargs: Any) -> Any:
        ...

    def emit(self, *args: Any) -> Any:
        ...


@runtime_checkable
class PMDASignaler(Protocol):
    """Declares the protocol for all signals that will be emitted from [`pymmcore_plus.mda.MDARunner`][]."""  # noqa: E501

    sequenceStarted: PSignalInstance
    """Emits `(sequence: MDASequence)` when an acquisition sequence is started."""
    sequencePauseToggled: PSignalInstance
    """Emits `(paused: bool)` when an acquisition sequence is paused or unpaused."""
    sequenceCanceled: PSignalInstance
    """Emits `(sequence: MDASequence)` when an acquisition sequence is canceled."""
    sequenceFinished: PSignalInstance
    """Emits `(sequence: MDASequence)` when an acquisition sequence is finished."""
    frameReady: PSignalInstance
    """Emits `(image: np.ndarray, event: MDAEvent)` after an image is acquired during an acquisition sequence."""  # noqa: E501
