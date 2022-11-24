import atexit
import contextlib
import subprocess
import sys
import threading
import time
from typing import Optional

from Pyro5 import api, core, errors
from typing_extensions import Protocol

from ..._logger import logger
from .. import server
from .._serialize import register_serializers


class CallbackProtocol(Protocol):
    def receive_core_callback(self, signal_name: str, args: tuple) -> None:
        """Will be called by server with name of signal, and tuple of args."""


def _get_auto_callback_class():
    for modname in {"PyQt5", "PySide2", "PyQt6", "PySide6"}:
        if qmodule := sys.modules.get(modname):
            QtWidgets = qmodule.QtWidgets
            if QtWidgets.QApplication.instance() is not None:
                from .callbacks.qcallback import QCoreSignaler

                return QCoreSignaler

    from .callbacks.basic import SynchronousCallback

    return SynchronousCallback


class RemoteMMCore(api.Proxy):
    def __init__(
        self,
        *,
        host: str = server.DEFAULT_HOST,
        port: int = server.DEFAULT_PORT,
        timeout: int = 5,
        verbose: bool = False,
        cleanup_new=True,
        connected_socket=None,
        callback_class=None,
    ):
        if callback_class is None:
            callback_class = _get_auto_callback_class()

        register_serializers()
        ensure_server_running(host, port, timeout, verbose, cleanup_new)

        uri = f"PYRO:{server.CORE_NAME}@{host}:{port}"
        super().__init__(uri, connected_socket=connected_socket)

        self.events = callback_class()
        cb_thread = DaemonThread(name="CallbackDaemon")
        cb_thread._daemon.register(self.events)
        self.connect_remote_callback(self.events)  # must come after register()
        cb_thread.start()

    def __getattr__(self, name):
        if name in ("events",):
            return object.__getattribute__(self, name)
        return super().__getattr__(name)

    def __setattr__(self, name, value):
        if name in ("events",):
            return object.__setattr__(self, name, value)
        return super().__setattr__(name, value)


def new_server_process(
    host: str, port: int, timeout: float = 5, verbose: bool = False
) -> subprocess.Popen:
    """Create a new daemon process."""
    cmd = [sys.executable, "-m", server.__name__, "-p", str(port), "--host", host]
    if verbose:
        cmd.append("--verbose")

    proc = subprocess.Popen(cmd)

    uri = f"PYRO:{core.DAEMON_NAME}@{host}:{port}"
    remote_daemon = api.Proxy(uri)

    while timeout > 0:
        try:
            remote_daemon.ping()
            return proc
        except Exception:
            timeout -= 0.1
            time.sleep(0.1)
    raise TimeoutError(f"Timeout connecting to server {uri}")


def ensure_server_running(
    host: str,
    port: int,
    timeout: int = 5,
    verbose: bool = False,
    cleanup_new: bool = True,
) -> Optional[subprocess.Popen]:
    """Ensure that a server daemon is running, or start one."""
    uri = f"PYRO:{core.DAEMON_NAME}@{host}:{port}"
    remote_daemon = api.Proxy(uri)
    try:
        remote_daemon.ping()
        logger.debug("Found existing server:\n{}", remote_daemon.info())
    except errors.CommunicationError:
        logger.debug("No server found, creating new mmcore server")
        proc = new_server_process(host, port, verbose=verbose)
        if cleanup_new:
            atexit.register(proc.kill)

            @atexit.register
            def _try_unload():
                with contextlib.suppress(errors.CommunicationError):
                    proxy = api.Proxy(f"PYRO:{server.CORE_NAME}@{host}:{port}")
                    proxy.unloadAllDevices()

        return proc
    return None


class DaemonThread(threading.Thread):
    def __init__(self, daemon: bool = True, name: str = "DaemonThread"):
        self._daemon = api.Daemon()
        self._stop_event = threading.Event()
        super().__init__(target=self._daemon.requestLoop, name=name, daemon=daemon)

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self.stop()
