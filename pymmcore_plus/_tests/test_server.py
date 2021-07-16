from unittest.mock import MagicMock

from pymmcore_plus.server import pyroCMMCore


def test_server():
    core = pyroCMMCore()
    core.loadSystemConfiguration("demo")

    assert core.getDeviceAdapterSearchPaths()
    cb = MagicMock()
    core.connect_remote_callback(cb)

    core.emit_signal("propertiesChanged")
    core.disconnect_remote_callback(cb)
