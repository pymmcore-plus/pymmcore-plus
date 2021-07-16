from typing import Set

from useq import MDASequence

from ..client._client import CallbackProtocol
from ..core._mmcore_plus import CMMCorePlus

_SIGNAL_NAMES: Set[str]

class pyroCMMCore(CMMCorePlus):
    def connect_remote_callback(self, handler: CallbackProtocol): ...
    def disconnect_remote_callback(self, handler: CallbackProtocol): ...
    def run_mda(self, sequence: MDASequence) -> None: ...
    def emit_signal(self, signal_name: str, *args) -> None: ...
