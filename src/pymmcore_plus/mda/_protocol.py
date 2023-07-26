from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from typing import TYPE_CHECKING, Iterable, Iterator

    from useq import MDAEvent, MDASequence


# NOTE: This whole thing could potentially go in useq-schema
# as it makes no assumptions about pymmcore-plus


@runtime_checkable
class PMDAEngine(Protocol):
    """Protocol that all MDA engines must implement."""

    @abstractmethod
    def setup_sequence(self, sequence: MDASequence) -> None:
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
        """

    @abstractmethod
    def exec_event(self, event: MDAEvent) -> object:
        """Execute `event`.

        This method is called after `setup_event` and is responsible for
        executing the event.  The default assumption is to acquire an image,
        but more elaborate events will be possible.

        The protocol for the returned object is still under development.  However, if
        the returned object has an `image` attribute, then the
        [`MDARunner`][pymmcore_plus.mda.MDARunner] will emit a
        [`frameReady`][pymmcore_plus.mda.PMDASignaler.frameReady] signal
        """
        # TODO: nail down a spec for the return object.

    def event_iterator(self, events: Iterable[MDAEvent]) -> Iterator[MDAEvent]:
        """Optional wrapper on the event iterator.

        This can be used to wrap the event iterator to perform any event merging
        (e.g. if the engine supports HardwareSequencing) or event modification.
        The default implementation is just `iter(events)`.

        Be careful when using this method.  It is powerful and can result in unexpected
        event iteration if used incorrectly.
        """
        yield from events


class FullPMDAEngine(PMDAEngine):
    """Optional methods that a PMDAEngine MAY implement."""

    def teardown_event(self, event: MDAEvent) -> None:
        """Teardown state of system (hardware, etc.) after `event`.

        If the engine provides this function, it will be called after
        `exec_event` to perform any cleanup or teardown required after
        the event has been executed.
        """

    def teardown_sequence(self, sequence: MDASequence) -> None:
        """Perform any teardown required after the sequence has been executed.

        If the engine provides this function, it will be called after the
        last event in the sequence has been executed.
        """
