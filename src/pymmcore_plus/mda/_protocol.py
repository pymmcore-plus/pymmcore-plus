from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from numpy.typing import NDArray
    from useq import MDAEvent, MDASequence

    from pymmcore_plus.metadata.schema import FrameMetaV1, SummaryMetaV1

    PImagePayload = tuple[NDArray, MDAEvent, FrameMetaV1]


# NOTE: This whole thing could potentially go in useq-schema
# as it makes no assumptions about pymmcore-plus


@runtime_checkable
class PMDAEngine(Protocol):
    """Protocol that all MDA engines must implement."""

    @abstractmethod
    def setup_sequence(self, sequence: MDASequence) -> SummaryMetaV1 | None:
        """Setup state of system (hardware, etc.) before an MDA is run.

        This method is called once at the beginning of a sequence.
        """

    @abstractmethod
    def setup_event(self, event: MDAEvent) -> None:
        """Prepare state of system (hardware, etc.) for `event`.

        This method is called before each event in the sequence.  It is
        responsible for preparing the state of the system for the event.
        The engine should be in a state where it can call `exec_event`
        without any additional preparation.  (This means that the engine
        should perform any waits or blocks required for system state
        changes to complete.)

        If the engine cannot set up the event (e.g. hardware failure), it may
        raise `SkipEvent(num_frames)` to tell the runner to skip this event
        and inform the data sink of the missing frames. If `SkipEvent` is raised,
        `exec_event` will NOT be called for this event, but `teardown_event` will be.
        """

    @abstractmethod
    def exec_event(self, event: MDAEvent) -> Iterable[PImagePayload | None]:
        """Execute `event`.

        This method is called after `setup_event` and is responsible for
        executing the event.  The default assumption is to acquire an image,
        but more elaborate events will be possible.

        Yields `(image, event, metadata)` tuples for each acquired frame.
        May yield `None` for frames that could not be acquired (e.g. partial
        hardware failure during a triggered sequence); the runner will call
        `sink.skip(frames=1)` for each `None`.
        """

    def event_iterator(self, events: Iterable[MDAEvent]) -> Iterator[MDAEvent]:
        """Wrapper on the event iterator.

        **Optional.**

        This can be used to wrap the event iterator to perform any event merging
        (e.g. if the engine supports HardwareSequencing) or event modification.
        The default implementation is just `iter(events)`.

        Be careful when using this method.  It is powerful and can result in unexpected
        event iteration if used incorrectly.
        """

    def teardown_event(self, event: MDAEvent) -> None:
        """Teardown state of system (hardware, etc.) after `event`.

        **Optional.**

        If the engine provides this function, it will be called after
        `exec_event` to perform any cleanup or teardown required after
        the event has been executed.
        """

    def teardown_sequence(self, sequence: MDASequence) -> None:
        """Perform any teardown required after the sequence has been executed.

        **Optional.**

        If the engine provides this function, it will be called after the
        last event in the sequence has been executed.
        """
