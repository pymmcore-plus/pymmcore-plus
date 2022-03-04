from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class PSignalInstance(Protocol):
    def connect(self, slot: Callable, **kwargs: Any):
        ...

    def disconnect(self, slot: Callable, **kwargs: Any):
        ...

    def emit(self, args: Any):
        ...


@runtime_checkable
class PMDASignaler(Protocol):
    sequenceStarted: PSignalInstance
    sequencePauseToggled: PSignalInstance
    sequenceCanceled: PSignalInstance
    sequenceFinished: PSignalInstance
    frameReady: PSignalInstance
