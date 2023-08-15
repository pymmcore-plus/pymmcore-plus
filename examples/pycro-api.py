from __future__ import annotations

import inspect
from queue import Queue
from typing import TYPE_CHECKING, Any, Callable, Iterable, Iterator, Sequence, cast

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine
from useq import MDAEvent

if TYPE_CHECKING:
    from collections import deque
    from typing import TypeAlias

    from numpy.typing import NDArray
    from pymmcore_plus.mda._engine import EventPayload

    Meta: TypeAlias = dict[str, Any]
    PycroEvent: TypeAlias = dict[str, Any]

    # Acquisition Hooks
    EventQueue = Queue[PycroEvent | None]
    EventHook = Callable[[PycroEvent], PycroEvent | None]
    EventQueueHook = Callable[[PycroEvent, EventQueue], PycroEvent | None]
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
        # we do the conversion below in the engine
        self._thread = self._core.run_mda(iter_queue)  # type: ignore

        self._image_process_fn = image_process_fn
        if image_process_fn is not None:
            sig = inspect.signature(image_process_fn)
            if len(sig.parameters) == 2:
                self._core.mda.events.frameReady.connect(self._call_img_hook_2arg)
            elif len(sig.parameters) == 3:
                self._core.mda.events.frameReady.connect(self._call_img_hook_3arg)
            else:
                raise ValueError(f"Invalid signature for image processing hook: {sig}")

    def _call_img_hook_2arg(self, img: NDArray, event: MDAEvent) -> None:
        hook = cast("ImgMetaHook", self._image_process_fn)
        hook(img, {})  # todo: meta

    def _call_img_hook_3arg(self, img: NDArray, event: MDAEvent) -> None:
        hook = cast("ImgMetaQueueHook", self._image_process_fn)
        hook(img, {}, self._event_queue)  # todo: meta

    def __enter__(self) -> Acquisition:
        return self

    def __exit__(self, *args: Any) -> None:
        self.mark_finished()
        self.await_completion()

    def acquire(self, event_or_events: PycroEvent | list[PycroEvent] | None) -> None:
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
    hook: AcquisitionHook | None, event: PycroEvent, queue: EventQueue
) -> PycroEvent | None:
    if hook is None:
        return event

    sig = inspect.signature(hook)
    if len(sig.parameters) == 1:
        return cast("EventHook", hook)(event)
    elif len(sig.parameters) == 2:
        return cast("EventQueueHook", hook)(event, queue)
    else:
        raise ValueError(f"Invalid signature for acquisition hook: {sig}")


PYCRO_KEY = "pycro_event"
SKIP = "pycro_skip"


def _build_engine(
    event_queue: EventQueue,
    event_generation_hook_fn: AcquisitionHook | None = None,
    pre_hardware_hook_fn: AcquisitionHook | None = None,
    post_hardware_hook_fn: AcquisitionHook | None = None,
    post_camera_hook_fn: AcquisitionHook | None = None,
) -> type[MDAEngine]:
    class PycroEngine(MDAEngine):
        def setup_event(self, event: MDAEvent) -> None:
            pyc_event = event.metadata[PYCRO_KEY]
            if pre_hardware_hook_fn is not None:
                pyc_event = _call_acq_hook(pre_hardware_hook_fn, pyc_event, event_queue)
                if pyc_event is None:
                    event.metadata[SKIP] = True
                    return
                event = _pycro_to_mda_event(pyc_event)

            super().setup_event(event)
            pyc_event = _call_acq_hook(post_hardware_hook_fn, pyc_event, event_queue)
            if pyc_event is None:
                event.metadata[SKIP] = True

        def exec_event(self, event: MDAEvent) -> EventPayload | None:
            if event.metadata.get(SKIP):
                return None

            result = super().exec_event(event)
            _call_acq_hook(post_camera_hook_fn, event.metadata[PYCRO_KEY], event_queue)
            return result

        def event_iterator(self, events: Iterable[MDAEvent]) -> Iterator[MDAEvent]:
            for pycro_event in iter(event_queue.get, None):
                _event = _call_acq_hook(
                    event_generation_hook_fn, pycro_event, event_queue
                )
                if _event is not None:
                    yield _pycro_to_mda_event(_event)

    return PycroEngine


def _pycro_to_mda_event(pycro_event: PycroEvent) -> MDAEvent:
    # TODO: convert between pycromanager event dict and MDAEvents
    # this will not work until that is done...

    # TODO: convert row/col to useq grid plan
    index = {
        k[0]: v
        for k, v in pycro_event["axes"].items()
        if k in ["z", "time", "position"]
        # TODO: convert channel str to index integer
    }
    if cfg := pycro_event.get("config_group", []):
        channel = {"group": cfg[0], "config": cfg[1]}
    else:
        channel = None

    return MDAEvent(
        index=index,
        channel=channel,
        x_pos=pycro_event.get("x"),
        y_pos=pycro_event.get("y"),
        z_pos=pycro_event.get("z"),
        exposure=pycro_event.get("exposure"),
        keep_shutter_open=pycro_event.get("keep_shutter_open", False),
        min_start_time=pycro_event.get("min_start_time"),
        properties=[tuple(prop) for prop in pycro_event.get("properties", [])],
        metadata={PYCRO_KEY: pycro_event},  # store original event
    )


if __name__ == "__main__":
    from pycromanager import multi_d_acquisition_events

    core = CMMCorePlus.instance()
    core.loadSystemConfiguration()

    with Acquisition() as acq:
        events = multi_d_acquisition_events(
            num_time_points=4,
            time_interval_s=2,
            channel_group="Channel",
            channels=["DAPI", "FITC"],
            z_start=0,
            z_end=6,
            z_step=0.4,
            order="tcz",
        )
        acq.acquire(events)
