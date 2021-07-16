from unittest.mock import MagicMock, patch

from pymmcore_plus.server import pyroCMMCore, serve


def test_server():
    core = pyroCMMCore()
    core.loadSystemConfiguration("demo")

    assert core.getDeviceAdapterSearchPaths()
    cb = MagicMock()
    core.connect_remote_callback(cb)

    core.emit_signal("propertiesChanged")
    core.disconnect_remote_callback(cb)


def test_serve(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["serve", "-p", "65111"])
    with patch("Pyro5.api.serve") as mock:
        serve()
    mock.assert_called_once()
