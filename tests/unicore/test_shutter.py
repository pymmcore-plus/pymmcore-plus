from __future__ import annotations

import pytest

from pymmcore_plus.experimental.unicore import ShutterDevice
from pymmcore_plus.experimental.unicore.core._unicore import UniMMCore

DEV = "ShutterDevice"


class MyShutterDevice(ShutterDevice):
    """Example State device (e.g., filter wheel, objective turret)."""

    _is_open: bool = False

    def set_open(self, open: bool) -> None:
        self._is_open = open

    def get_open(self) -> bool:
        return self._is_open


def _load_state_device(core: UniMMCore, adapter: MyShutterDevice | None = None) -> None:
    """Load either a Python or C++ State device."""
    if DEV in core.getLoadedDevices():
        core.unloadDevice(DEV)

    if adapter is not None:
        core.loadPyDevice(DEV, adapter)
    else:
        core.loadDevice(DEV, "DemoCamera", "DShutter")
    core.initializeDevice(DEV)


@pytest.fixture(params=["python", "cpp"])
def unicore(request: pytest.FixtureRequest) -> UniMMCore:
    """Fixture providing a core with a loaded state device."""
    core = UniMMCore()
    dev = MyShutterDevice() if request.param == "python" else None
    _load_state_device(core, dev)
    # Store the parameter type for easy access in tests
    core._test_device_type = request.param  # type: ignore[assignment]
    return core


def test_shutter_device_basic_functionality(unicore: UniMMCore) -> None:
    """Test basic state device operations."""

    assert not unicore.getShutterDevice()
    unicore.setShutterDevice(DEV)
    assert unicore.getShutterDevice() == DEV
    assert unicore.getShutterOpen() is False
    unicore.setShutterOpen(True)
    assert unicore.getShutterOpen() is True
    unicore.setShutterOpen(False)
    assert unicore.getShutterOpen() is False
