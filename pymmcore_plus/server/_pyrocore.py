from functools import partial
from typing import TYPE_CHECKING, Set

from Pyro5 import errors
from Pyro5.api import behavior, expose, oneway

from .._util import wrap_for_pyro
from ..core._mmcore_plus import CMMCorePlus
from ..core._signals import _CMMCoreSignaler

if TYPE_CHECKING:
    from ..client._client import CallbackProtocol


_SIGNAL_NAMES = {name for name in dir(_CMMCoreSignaler) if not name.startswith("_")}


@expose
@behavior(instance_mode="single")
@wrap_for_pyro
class pyroCMMCore(CMMCorePlus):
    """CMMCorePlus instance running on a server.

    It should mostly mimic CMMCorePlus but it may have some additional characteristics
    that are only necessary for asynchronous/remote usage (like callbacks)
    """

    _callback_handlers: Set["CallbackProtocol"] = set()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in _SIGNAL_NAMES:
            getattr(self, name).connect(partial(self._emit_signal, name))

    def connect_remote_callback(self, handler: "CallbackProtocol"):
        self._callback_handlers.add(handler)

    def disconnect_remote_callback(self, handler: "CallbackProtocol"):
        self._callback_handlers.discard(handler)

    @oneway
    def run_mda(self, sequence) -> None:
        return super().run_mda(sequence)

    @oneway
    def _emit_signal(self, signal_name: str, *args):
        from loguru import logger

        logger.debug("{}: {}", signal_name, args)
        for handler in list(self._callback_handlers):
            try:
                handler._pyroClaimOwnership()
                handler.receive_core_callback(signal_name, args)
            except errors.CommunicationError:
                self.disconnect_remote_callback(handler)
