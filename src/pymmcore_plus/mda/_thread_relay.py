from __future__ import annotations

import threading
import time
from collections import deque
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Literal, overload

from pymmcore_plus._util import listeners_connected

from .events import _get_auto_MDA_callback_class

if TYPE_CHECKING:
    from collections.abc import Iterator
    from contextlib import AbstractContextManager
    from typing import Any

    from pymmcore_plus.core.events._protocol import PSignalInstance
    from pymmcore_plus.mda import PMDASignaler


@overload
def mda_listeners_connected(
    *listeners: Any,
    mda_events: PMDASignaler | None = ...,
    name_map: dict[str, str] | None = ...,
    asynchronous: Literal[False],
    wait_on_exit: bool = ...,
) -> AbstractContextManager[None]: ...


@overload
def mda_listeners_connected(
    *listeners: Any,
    mda_events: PMDASignaler | None = ...,
    name_map: dict[str, str] | None = ...,
    asynchronous: Literal[True] = ...,
    wait_on_exit: bool = ...,
) -> AbstractContextManager[MDARelayThread]: ...


@contextmanager
def mda_listeners_connected(
    *listeners: Any,
    mda_events: PMDASignaler | None = None,
    name_map: dict[str, str] | None = None,
    asynchronous: bool = True,
    wait_on_exit: bool = True,
) -> Iterator:
    """Context in which MDA events are connected to listeners, in a thread by default.

    Parameters
    ----------
    listeners : Any
        Object(s) that has methods matching the name of signals on `mda_events`.
        (Namely: `sequenceStarted`, `frameReady`, `sequenceFinished`, etc...)
    mda_events : PMDASignaler | None, optional
        The MDA events to connect to.  If not provided, the `mda.events` attribute on
        the global `CMMCorePlus.instance()` will be used, by default None.
    name_map : dict[str, str] | None
        Optionally map signal names to different method names on `listener`.  This
        can be used to connect callbacks with different names. By default, the
        callbacks names must match the signal names exactly.
    asynchronous : bool, optional
        Whether to execute callbacks on `listeners` in another thread.  If True,
        the MDA will proceed without waiting for the callbacks to finish.  A deque will
        collect events and pass them to handlers as they become ready (FIFO),
        by default True.
    wait_on_exit : bool, optional
        Whether to wait for all callbacks on listeners to finish before exiting the
        context, by default True.
    """
    if mda_events is None:
        from pymmcore_plus import CMMCorePlus

        mda_events = CMMCorePlus.instance().mda.events

    if not asynchronous:
        # Just collapse to a regular synchronous listeners_connected
        with listeners_connected(mda_events, *listeners, name_map=name_map):
            yield None
        return

    # create a relay thread and start/stop it when the sequence starts/finishes
    relay = MDARelayThread(type(mda_events))
    mda_events.sequenceStarted.connect(relay.start)
    mda_events.sequenceFinished.connect(relay.stop)

    try:
        # connect the actual core.mda.events to methods on the relay
        with listeners_connected(mda_events, relay):
            # connect the signals on the relay to the listeners
            with listeners_connected(
                relay.signals,
                *listeners,
                name_map=name_map,
                qt_connection_type="DirectConnection",
            ):
                yield relay

                if wait_on_exit:
                    # wait for the relay to finish
                    if relay.is_alive():
                        relay.join()
                elif relay.remaining():
                    ...  # TODO: log reminaing events
    finally:
        # disconnect the relay
        with suppress(Exception):
            mda_events.sequenceStarted.disconnect(relay.start)
            mda_events.sequenceFinished.disconnect(relay.stop)


class MDARelayThread(threading.Thread):
    """A thread that relays MDA events to a signaler.

    Meant to be used with `mda_listeners_connected` to connect MDA events to
    listeners that don't implement asynchronous callbacks.

    Parameters
    ----------
    sleep_interval : float, optional
        The interval in seconds to sleep between processing events, by default 0.005
    """

    def __init__(
        self,
        signal_class: type[PMDASignaler] | None = None,
        sleep_interval: float = 0.005,
    ) -> None:
        super().__init__()
        if signal_class is None:
            signal_class = _get_auto_MDA_callback_class()
        self.signals = signal_class()

        self._sleep_interval = sleep_interval
        self._deque: deque[tuple[str, tuple[Any, ...]]] = deque()
        self._stop_event = threading.Event()

    def run(self) -> None:
        """Block until the stop event is set and the deque is empty."""
        while self._deque or not self._stop_event.is_set():
            if self._deque:
                signal_name, args = self._deque.popleft()
                emitter: PSignalInstance = getattr(self.signals, signal_name)
                emitter.emit(*args)
            else:
                time.sleep(self._sleep_interval)

    def remaining(self) -> int:
        """Return the number of events remaining to be processed."""
        return len(self._deque)

    def stop(self) -> None:
        """Set the stop event to stop the thread."""
        self._stop_event.set()

    # MDA callbacks
    # These may be connected to core.mda.events using `listeners_connected`
    # as done above in `mda_listeners_connected`

    def sequenceStarted(self, *args: Any) -> None:
        self._deque.append(("sequenceStarted", args))

    def frameReady(self, *args: Any) -> None:
        self._deque.append(("frameReady", args))

    def sequencePauseToggled(self, *args: Any) -> None:
        self._deque.append(("sequencePauseToggled", args))

    def sequenceCanceled(self, *args: Any) -> None:
        self._deque.append(("sequenceCanceled", args))

    def sequenceFinished(self, *args: Any) -> None:
        self._deque.append(("sequenceFinished", args))
