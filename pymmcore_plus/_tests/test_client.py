import os
from pathlib import Path

import numpy as np
import pytest
from useq import MDAEvent, MDASequence

import pymmcore_plus
from pymmcore_plus.client import RemoteMMCore
from pymmcore_plus.client.callbacks.basic import SynchronousCallback
from pymmcore_plus.client.callbacks.qcallback import QCoreCallback
from pymmcore_plus.server import DEFAULT_URI

if not os.getenv("MICROMANAGER_PATH"):
    try:
        sfx = "_win" if os.name == "nt" else "_mac"
        root = Path(pymmcore_plus.__file__).parent.parent
        mm_path = list(root.glob(f"**/Micro-Manager-*{sfx}"))[0]
        os.environ["MICROMANAGER_PATH"] = str(mm_path)
    except IndexError:
        raise AssertionError(
            "MICROMANAGER_PATH env var was not set, and Micro-Manager "
            "installation was not found in this package.  Please run "
            "`python micromanager_gui/install_mm.py"
        )


@pytest.fixture
def proxy():
    with RemoteMMCore() as mmcore:
        mmcore.loadSystemConfiguration()
        yield mmcore


def test_client(proxy):
    assert str(proxy._pyroUri) == DEFAULT_URI
    proxy.getConfigGroupState("Channel")


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
        proxy.events.sequenceStarted,
        proxy.events.frameReady,
        proxy.events.frameReady,
        proxy.events.sequenceFinished,
    ]
    checks = [_check_seq, _check_frame, _check_frame, _check_seq]

    with qtbot.waitSignals(signals, check_params_cbs=checks, order="strict"):
        proxy.run_mda(mda)


# test canceling while waiting for the next time point
def test_mda_cancel(qtbot, proxy: RemoteMMCore):
    mda = MDASequence(time_plan={"interval": 5000, "loops": 3})
    with qtbot.waitSignal(proxy.events.sequenceStarted):
        proxy.run_mda(mda)
    with qtbot.waitSignals(
        [proxy.events.sequenceFinished, proxy.events.sequenceCanceled], timeout=500
    ):
        proxy.cancel()


# TODO: this test may accidentally pass if qtbot is created before this
@pytest.mark.xfail(
    reason="synchronous callbacks not working yet", raises=AssertionError, strict=True
)
def test_cb_without_qt(proxy):
    """This tests that we can call a core method within a callback

    currently only works for Qt callbacks... need to figure out synchronous approach.
    """
    assert isinstance(proxy.events, SynchronousCallback)
    cam = [None]

    @proxy.events.systemConfigurationLoaded.connect
    def _cb():
        cam[0] = proxy.getCameraDevice()

    proxy.loadSystemConfiguration()
    assert cam[0] == "Camera"


def test_cb_with_qt(qtbot, proxy):
    """This tests that we can call a core method within a callback

    currently only works for Qt callbacks... need to figure out synchronous approach.
    """
    # because we're running with qt active
    assert isinstance(proxy.events, QCoreCallback)
    cam = [None]

    @proxy.events.systemConfigurationLoaded.connect
    def _cb():
        cam[0] = proxy.getCameraDevice()

    with qtbot.waitSignal(proxy.events.systemConfigurationLoaded):
        proxy.loadSystemConfiguration()
    assert cam[0] == "Camera"
