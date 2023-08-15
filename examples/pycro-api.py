from __future__ import annotations

import inspect
from queue import Queue
from typing import TYPE_CHECKING, Any, Callable, Iterable, Iterator, Sequence, cast

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine

if TYPE_CHECKING:
    from collections import deque
    from typing import TypeAlias

    from numpy.typing import NDArray
    from pymmcore_plus.mda._engine import EventPayload
    from useq import MDAEvent

    Meta: TypeAlias = dict[str, Any]
    Event: TypeAlias = dict[str, Any]

    # Acquisition Hooks
    EventQueue = Queue[Event | None]
    EventHook = Callable[[Event], Event | None]
    EventQueueHook = Callable[[Event, EventQueue], Event | None]
    AcquisitionHook = EventHook | EventQueueHook

    # Processor Hooks
    ImgHookReturn = tuple[NDArray, Meta] | Sequence[tuple[NDArray, Meta]] | None
    ImgMetaHook = Callable[[NDArray, Meta], ImgHookReturn]
    ImgMetaQueueHook = Callable[[NDArray, Meta, EventQueue], ImgHookReturn]
    ProcessorHook = ImgMetaHook | ImgMetaQueueHook


class Acquisition:
    """Pycro-Manager -> pymmcore-plus adaptor."""

    def __init__(
        self,
        image_process_fn: ProcessorHook | None = None,
        event_generation_hook_fn: AcquisitionHook | None = None,
        pre_hardware_hook_fn: AcquisitionHook | None = None,
        post_hardware_hook_fn: AcquisitionHook | None = None,
        post_camera_hook_fn: AcquisitionHook | None = None,
    ):
        self._core = CMMCorePlus.instance()
        self._event_queue: EventQueue = Queue()
        self._engine_cls = _build_engine(
            self._event_queue,
            event_generation_hook_fn,
            pre_hardware_hook_fn,
            post_hardware_hook_fn,
            post_camera_hook_fn,
        )
        self._engine = self._engine_cls(self._core)
        self._core.mda.set_engine(self._engine)

        iter_queue = iter(self._event_queue.get, None)
        # type error because of conversion between MDAEvent and pycromanager dict.
        self._thread = self._core.run_mda(iter_queue)

        # TODO:
        # connect image_process_fn to `core.mda.frameReady`

    def __enter__(self) -> Acquisition:
        return self

    def __exit__(self, *args: Any) -> None:
        self.mark_finished()
        self.await_completion()

    def acquire(self, event_or_events: Event | list[Event] | None) -> None:
        if isinstance(event_or_events, list):
            for event in event_or_events:
                self._event_queue.put(event)
        else:
            self._event_queue.put(event_or_events)

    def abort(self, exception: BaseException | None = None) -> None:
        self._core.mda.cancel()
        cast("deque", self._event_queue.queue).clear()

    def await_completion(self) -> None:
        self._thread.join()

    def mark_finished(self) -> None:
        self._event_queue.put(None)


# note, we don't need to check signature every time...
def _call_acq_hook(
    hook: AcquisitionHook | None, event: Event, queue: EventQueue
) -> Event | None:
    if hook is None:
        return event

    sig = inspect.signature(hook)
    if len(sig.parameters) == 1:
        return cast("EventHook", hook)(event)
    elif len(sig.parameters) == 2:
        return cast("EventQueueHook", hook)(event, queue)
    else:
        raise ValueError(f"Invalid signature for acquisition hook: {sig}")


def _build_engine(
    event_queue: EventQueue,
    event_generation_hook_fn: AcquisitionHook | None = None,
    pre_hardware_hook_fn: AcquisitionHook | None = None,
    post_hardware_hook_fn: AcquisitionHook | None = None,
    post_camera_hook_fn: AcquisitionHook | None = None,
) -> type[MDAEngine]:
    # TODO: convert between pycromanager event dict and MDAEvents
    # this will not work until that is done...

    class PycroEngine(MDAEngine):
        def setup_event(self, event: Event) -> None:
            _event = _call_acq_hook(pre_hardware_hook_fn, event, event_queue)
            if _event is None:
                # TODO: skip event
                return

            super().setup_event(_event)
            _event = _call_acq_hook(post_hardware_hook_fn, event, event_queue)
            if _event is None:
                # TODO: skip event
                return

        def exec_event(self, event: Event) -> EventPayload | None:
            result = super().exec_event(event)
            _call_acq_hook(post_camera_hook_fn, event, event_queue)
            return result

        def event_iterator(self, events: Iterable[Event]) -> Iterator[MDAEvent]:
            for event in iter(event_queue.get, None):
                _event = _call_acq_hook(event_generation_hook_fn, event, event_queue)
                if _event is not None:
                    yield _event

    return PycroEngine
