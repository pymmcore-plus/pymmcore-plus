import socket
import threading
from subprocess import Popen
from typing import Any, Type

from Pyro5 import api
from typing_extensions import Protocol as Protocol

from .._serialize import register_serializers as register_serializers
from ..core import CMMCorePlus

class CallbackProtocol(Protocol):
    def receive_core_callback(self, signal_name: str, args: tuple) -> None: ...

# doesn't actually subclass, but has same methods
class RemoteMMCore(api.Proxy, CMMCorePlus):
    def __init__(
        self,
        *,
        host=...,
        port=...,
        timeout: int = ...,
        verbose: bool = ...,
        cleanup_new: bool = ...,
        cleanup_existing: bool = ...,
        connected_socket: socket.socket | None = ...
    ) -> None: ...
    def _register_callback(self, callback: CallbackProtocol): ...

def new_server_process(
    host: str, port: int, timeout: int = ..., verbose: bool = ...
) -> Popen: ...
def ensure_server_running(
    host: str,
    port: int,
    timeout: int = ...,
    verbose: bool = ...,
    cleanup_new: bool = ...,
    cleanup_existing: bool = ...,
) -> Popen | None: ...

class DaemonThread(threading.Thread):
    def __init__(self, daemon: bool = ...) -> None: ...
    def __enter__(self): ...
    def __exit__(self, *args, **kwargs) -> None: ...
    _daemon: api.Daemon
    _stop_event: threading.Event
