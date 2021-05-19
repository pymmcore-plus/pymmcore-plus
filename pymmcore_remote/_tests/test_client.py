import atexit

import numpy as np
import pytest
from useq import MDAEvent, MDASequence

from pymmcore_remote._client import RemoteMMCore, new_server_process
from pymmcore_remote._server import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_URI
from pymmcore_remote.qcallbacks import QCoreCallback


@pytest.fixture(scope="session")
def server():
    proc = new_server_process(DEFAULT_HOST, DEFAULT_PORT)
    atexit.register(proc.kill)


@pytest.fixture
def proxy(server):
    with RemoteMMCore() as mmcore:
        mmcore.loadSystemConfiguration()
        yield mmcore


def test_client(proxy):
    assert str(proxy._pyroUri) == DEFAULT_URI


def test_mda(qtbot, proxy):
    mda = MDASequence(time_plan={"interval": 0.1, "loops": 2})
    cb = QCoreCallback()
    proxy.register_callback(cb)

    def _test_signal(img, event):
        return (
            isinstance(img, np.ndarray)
            and isinstance(event, MDAEvent)
            and event.sequence == mda
            and event.sequence is not mda
        )

    signals = [cb.MDAFrameReady, cb.MDAFrameReady]
    checks = [_test_signal, _test_signal]

    with qtbot.waitSignals(signals, check_params_cbs=checks, order="strict"):
        proxy.run_mda(mda)
