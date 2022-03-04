import numpy as np
import pytest
from useq import MDAEvent, MDASequence

pytest.importorskip("Pyro5")
from pymmcore_plus.remote import RemoteMMCore  # noqa
from pymmcore_plus.remote.client.callbacks.basic import SynchronousCallback  # noqa
from pymmcore_plus.remote.client.callbacks.qcallback import QCoreSignaler  # noqa
from pymmcore_plus.remote.server import DEFAULT_URI  # noqa


@pytest.fixture
def proxy():
    with RemoteMMCore() as mmcore:
        mmcore.loadSystemConfiguration()
        yield mmcore


def test_client(proxy):
    assert str(proxy._pyroUri) == DEFAULT_URI
    proxy.getConfigGroupState("Channel")


@pytest.mark.skip(reason="mda not being properly exposed")
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
    signals = [
        (proxy.events.sequenceStarted, "started"),
        (proxy.events.frameReady, "frameReady1"),
        (proxy.events.frameReady, "frameReady2"),
        (proxy.events.sequenceFinished, "finishd"),
    ]
    checks = [_check_seq, _check_frame, _check_frame, _check_seq]

    with qtbot.waitSignals(signals, check_params_cbs=checks, order="strict"):
        proxy.run_mda(mda)


# test canceling while waiting for the next time point
@pytest.mark.skip(reason="mda not being properly exposed")
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
    assert isinstance(proxy.events, QCoreSignaler)
    cam = [None]

    @proxy.events.systemConfigurationLoaded.connect
    def _cb():
        cam[0] = proxy.getCameraDevice()

    with qtbot.waitSignal(proxy.events.systemConfigurationLoaded):
        proxy.loadSystemConfiguration()
    assert cam[0] == "Camera"
