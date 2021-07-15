import pytest

from pymmcore_plus import RemoteMMCore
from pymmcore_plus.client.callbacks.basic import SynchronousCallback
from pymmcore_plus.client.callbacks.qcallback import QCoreCallback


# TODO: this test may accidentally pass if qtbot is created before this
@pytest.mark.xfail(reason="synchronous callbacks not working yet")
def test_cb_without_qt():
    """This tests that we can call a core method within a callback

    currently only works for Qt callbacks... need to figure out synchronous approach.
    """
    with RemoteMMCore() as core:
        assert isinstance(core.events, SynchronousCallback)
        cam = [None]

        @core.events.systemConfigurationLoaded.connect
        def _cb():
            cam[0] = core.getCameraDevice()

        core.loadSystemConfiguration()
        assert cam[0] == "Camera"


def test_cb_with_qt(qtbot):
    """This tests that we can call a core method within a callback

    currently only works for Qt callbacks... need to figure out synchronous approach.
    """
    with RemoteMMCore() as core:
        assert isinstance(core.events, QCoreCallback)
        cam = [None]

        @core.events.systemConfigurationLoaded.connect
        def _cb():
            cam[0] = core.getCameraDevice()

        with qtbot.waitSignal(core.events.systemConfigurationLoaded):
            core.loadSystemConfiguration()
        assert cam[0] == "Camera"
