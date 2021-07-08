import atexit
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING, Optional

from loguru import logger
from Pyro5 import api, core, errors
from typing_extensions import Protocol

from .. import server
from .._serialize import register_serializers
from ..core._signals import _CMMCoreSignaler

if TYPE_CHECKING:
    from psutil import Process


class CallbackProtocol(Protocol):
    def receive_core_callback(self, signal_name: str, args: tuple) -> None:
        """Will be called by server with name of signal, and tuple of args."""


class _CBrelay(CallbackProtocol):
    def __init__(self, proxy: _CMMCoreSignaler) -> None:
        super().__init__()
        self._proxy = proxy

    def receive_core_callback(self, signal_name: str, args: tuple) -> None:
        """Will be called by server with name of signal, and tuple of args."""
        getattr(self._proxy, signal_name).emit(*args)


class RemoteMMCore(api.Proxy, _CMMCoreSignaler):
    def __init__(
        self,
        *,
        host: str = server.DEFAULT_HOST,
        port: int = server.DEFAULT_PORT,
        timeout: int = 5,
        verbose: bool = False,
        cleanup_new=True,
        cleanup_existing=True,
        connected_socket=None,
    ):
        register_serializers()
        ensure_server_running(
            host, port, timeout, verbose, cleanup_new, cleanup_existing
        )

        uri = f"PYRO:{server.CORE_NAME}@{host}:{port}"
        super().__init__(uri, connected_socket=connected_socket)

        self._cb_thread = None
        self._callbacks = set()
        self._register_callback(_CBrelay(self))

    def _register_callback(self, callback: CallbackProtocol):
        """Register callback object in proxy process to receive remote callbacks.

        Not to be confused with `mmcore.registerCallback`, which is only used once by
        CMMCorePlus to receive events coming from the internal C++ CMMcore object.

        Note: RemoteMMCore automatically behaves as a callback receiver, you can
        connect to any of the signals already provided by `CMMCorePlus`:

            proxy = RemoteMMCore()
            proxy.systemConfigurationLoaded.connect(lambda: print("loaded!"))


        Parameters
        ----------
        callback : CallbackProtocol
            Just an object that has a `receive_core_callback` method. When a remote
            callback is received by this proxy, it will call this method as:
            `callback.receive_core_callback(signal_name, args)`

        Raises
        ------
        TypeError
            If the provided object doesn't have a `receive_core_callback` method.
        """
        class_cb = getattr(type(callback), "receive_core_callback", None)
        if class_cb is None:
            raise TypeError("Callbacks must have a 'receive_core_callback' method.")
        if not hasattr(class_cb, "_pyroExposed"):
            class_cb._pyroExposed = True

        self._callbacks.add(callback)
        self._cb_thread = DaemonThread()
        self._cb_thread._daemon.register(callback)
        self.connect_remote_callback(callback)  # must come after register()
        self._cb_thread.start()

    def __exit__(self, *args):
        logger.debug("closing pyro client")
        for cb in self._callbacks:
            self.disconnect_remote_callback(cb)
        if self._cb_thread is not None:
            self._cb_thread._daemon.close()
        super().__exit__(*args)

    def __getattr__(self, name):
        if name in ("_cb_thread", "_callbacks"):
            return object.__getattribute__(self, name)
        return super().__getattr__(name)

    def __setattr__(self, name, value):
        if name in ("_cb_thread", "_callbacks"):
            return object.__setattr__(self, name, value)
        return super().__setattr__(name, value)


def _get_remote_pid(host, port) -> Optional["Process"]:
    import psutil

    for proc in psutil.process_iter(["connections"]):
        for pconn in proc.info["connections"] or []:
            if pconn.laddr.port == port and pconn.laddr.ip == host:
                return proc


def new_server_process(
    host: str, port: int, timeout=5, verbose=False
) -> subprocess.Popen:
    """Create a new daemon process"""
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
    host, port, timeout=5, verbose=False, cleanup_new=True, cleanup_existing=False
) -> Optional[subprocess.Popen]:
    """Ensure that a server daemon is running, or start one."""
    uri = f"PYRO:{core.DAEMON_NAME}@{host}:{port}"
    remote_daemon = api.Proxy(uri)
    try:
        remote_daemon.ping()
        logger.debug("Found existing server:\n{}", remote_daemon.info())
        if cleanup_existing:
            proc = _get_remote_pid(host, port)
            if proc is not None:
                atexit.register(proc.kill)
    except errors.CommunicationError:
        logger.debug("No server found, creating new mmcore server")
        proc = new_server_process(host, port, verbose=verbose)
        if cleanup_new:
            atexit.register(proc.kill)
        return proc


class DaemonThread(threading.Thread):
    def __init__(self, daemon=True):
        self._daemon = api.Daemon()
        self._stop_event = threading.Event()
        super().__init__(
            target=self._daemon.requestLoop, name="DaemonThread", daemon=daemon
        )

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self.stop()
