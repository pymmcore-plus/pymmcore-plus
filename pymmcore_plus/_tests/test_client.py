import atexit
import os
from pathlib import Path

import numpy as np
import pytest
from useq import MDAEvent, MDASequence

import pymmcore_plus
from pymmcore_plus.client import RemoteMMCore
from pymmcore_plus.client._client import new_server_process
from pymmcore_plus.server import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_URI

if not os.getenv("MICROMANAGER_PATH"):
    try:
        root = Path(pymmcore_plus.__file__).parent.parent
        mm_path = list(root.glob("**/Micro-Manager-*"))[0]
        os.environ["MICROMANAGER_PATH"] = str(mm_path)
    except IndexError:
        raise AssertionError(
            "MICROMANAGER_PATH env var was not set, and Micro-Manager "
            "installation was not found in this package.  Please run "
            "`python micromanager_gui/install_mm.py"
        )


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

    def _check_frame(img, event):
        return (
            isinstance(img, np.ndarray)
            and isinstance(event, MDAEvent)
            and event.sequence == mda
            and event.sequence is not mda
        )

    def _check_seq(obj):
        return obj.uid == mda.uid

    signals = [
        proxy.sequenceStarted,
        proxy.frameReady,
        proxy.frameReady,
        proxy.sequenceFinished,
    ]
    checks = [_check_seq, _check_frame, _check_frame, _check_seq]

    with qtbot.waitSignals(signals, check_params_cbs=checks, order="strict"):
        proxy.run_mda(mda)
