from Pyro5 import api

from ....core.events import CMMCoreSignaler


class SynchronousCallback(CMMCoreSignaler):
    def __init__(self) -> None:
        super().__init__()

    @api.expose
    def receive_core_callback(self, signal_name: str, args: tuple) -> None:
        """Will be called by server with name of signal, and tuple of args."""
        getattr(self, signal_name).emit(*args)
