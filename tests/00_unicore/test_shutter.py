from __future__ import annotations

import time
from typing import TYPE_CHECKING

import numpy as np
import pytest

from pymmcore_plus.experimental.unicore import CameraDevice, ShutterDevice
from pymmcore_plus.experimental.unicore.core._unicore import UniMMCore

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from numpy.typing import DTypeLike

DEV = "ShutterDevice"
CAM = "Camera"

SENSOR_SHAPE = (64, 64)
DTYPE = np.uint16


class MyShutterDevice(ShutterDevice):
    """Example shutter device."""

    _is_open: bool = False
    open_count: int = 0
    close_count: int = 0

    def set_open(self, open: bool) -> None:
        self._is_open = open
        if open:
            self.open_count += 1
        else:
            self.close_count += 1

    def get_open(self) -> bool:
        return self._is_open


class MyCamera(CameraDevice):
    """Minimal camera for autoshutter tests."""

    _exposure: float = 10.0

    def get_exposure(self) -> float:
        return self._exposure

    def set_exposure(self, exposure: float) -> None:
        self._exposure = exposure

    _binning: int = 1

    def get_binning(self) -> int:
        return self._binning

    def set_binning(self, value: int) -> None:
        self._binning = value

    def shape(self) -> tuple[int, int]:
        return SENSOR_SHAPE

    def dtype(self) -> np.dtype:
        return np.dtype(DTYPE)

    def start_sequence(
        self,
        n_images: int | None = None,
        get_buffer: None | (callable[[Sequence[int], DTypeLike], np.ndarray]) = None,
    ) -> Iterator[dict]:
        i = 0
        while n_images is None or i < n_images:
            buf = get_buffer(SENSOR_SHAPE, DTYPE) if get_buffer else None
            if buf is not None:
                buf[:] = 1
            yield {}
            i += 1


def _load_shutter(core: UniMMCore, adapter: MyShutterDevice | None = None) -> None:
    """Load either a Python or C++ Shutter device."""
    if DEV in core.getLoadedDevices():
        core.unloadDevice(DEV)

    if adapter is not None:
        core.loadPyDevice(DEV, adapter)
    else:
        core.loadDevice(DEV, "DemoCamera", "DShutter")
    core.initializeDevice(DEV)


@pytest.fixture(params=["python", "cpp"])
def unicore(request: pytest.FixtureRequest) -> UniMMCore:
    """Fixture providing a core with a loaded shutter device."""
    core = UniMMCore()
    dev = MyShutterDevice() if request.param == "python" else None
    _load_shutter(core, dev)
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


def test_set_shutter_device_via_set_property():
    """setProperty('Core', 'Shutter', label) should route to setShutterDevice."""
    core = UniMMCore()
    core.loadPyDevice(DEV, MyShutterDevice())
    core.initializeDevice(DEV)

    core.setProperty("Core", "Shutter", DEV)

    assert core.getShutterDevice() == DEV


# ---------------------------------------------------------------------------
# autoShutter tests
# ---------------------------------------------------------------------------

CPP_CAM = "DCam"
CPP_SHUTTER = "DShutter"


def _make_core(
    cam_type: str, shutter_type: str
) -> tuple[UniMMCore, MyShutterDevice | None]:
    """Create a UniMMCore with the requested camera/shutter combo.

    cam_type and shutter_type are each "py" or "cpp".
    Returns (core, py_shutter_or_None).
    """
    core = UniMMCore()

    # Load shutter
    py_shutter: MyShutterDevice | None = None
    if shutter_type == "py":
        py_shutter = MyShutterDevice()
        core.loadPyDevice(DEV, py_shutter)
        core.initializeDevice(DEV)
        core.setShutterDevice(DEV)
    else:
        core.loadDevice(CPP_SHUTTER, "DemoCamera", "DShutter")
        core.initializeDevice(CPP_SHUTTER)
        core.setShutterDevice(CPP_SHUTTER)

    # Load camera
    if cam_type == "py":
        core.loadPyDevice(CAM, MyCamera())
        core.initializeDevice(CAM)
        core.setCameraDevice(CAM)
    else:
        core.loadDevice(CPP_CAM, "DemoCamera", "DCam")
        core.initializeDevice(CPP_CAM)
        core.setCameraDevice(CPP_CAM)

    return core, py_shutter


def test_autoshutter_set_property():
    """setProperty('Core', 'AutoShutter', '0'/'1') routes to setAutoShutter."""
    core = UniMMCore()
    assert core.getAutoShutter() is True

    core.setProperty("Core", "AutoShutter", "0")
    assert core.getAutoShutter() is False

    core.setProperty("Core", "AutoShutter", "1")
    assert core.getAutoShutter() is True


@pytest.mark.parametrize("cam_type", ["py", "cpp"])
@pytest.mark.parametrize("shutter_type", ["py", "cpp"])
def test_autoshutter_snap_all_combos(cam_type: str, shutter_type: str) -> None:
    """snapImage opens/closes the shutter in all cam/shutter combinations.

    Verified via propertyChanged signals emitted by CMMCorePlus.snapImage:
    the shutter "State" should go "1" (open) then "0" (close) around the snap,
    with an imageSnapped signal in between.
    """
    core, _ = _make_core(cam_type, shutter_type)
    shutter_label = core.getShutterDevice()

    events: list[str] = []
    core.events.propertyChanged.connect(
        lambda dev, prop, val: (
            events.append(f"{dev}.{prop}={val}")
            if dev == shutter_label and prop == "State"
            else None
        )
    )
    core.events.imageSnapped.connect(lambda _cam: events.append("imageSnapped"))

    core.snapImage()

    assert events == [
        f"{shutter_label}.State=1",
        "imageSnapped",
        f"{shutter_label}.State=0",
    ]

    # Also verify the shutter is actually closed now
    assert core.getShutterOpen() is False


@pytest.mark.parametrize("cam_type", ["py", "cpp"])
@pytest.mark.parametrize("shutter_type", ["py", "cpp"])
def test_autoshutter_off_snap_does_not_touch_shutter(
    cam_type: str, shutter_type: str
) -> None:
    """snapImage should NOT open/close shutter when autoShutter is off."""
    core, _ = _make_core(cam_type, shutter_type)
    core.setAutoShutter(False)
    shutter_label = core.getShutterDevice()

    events: list[str] = []
    core.events.propertyChanged.connect(
        lambda dev, prop, val: (
            events.append(f"{dev}.{prop}={val}")
            if dev == shutter_label and prop == "State"
            else None
        )
    )

    core.snapImage()

    # No shutter state changes should have been emitted
    shutter_events = [e for e in events if "State=" in e]
    assert shutter_events == []


def test_autoshutter_sequence_acquisition():
    """Sequence acquisition should open shutter on start, close on stop."""
    core, shutter = _make_core("py", "py")
    assert shutter is not None

    core.startSequenceAcquisition(3, 0, True)
    assert shutter.open_count == 1
    assert shutter._is_open

    while core.isSequenceRunning():
        time.sleep(0.001)
    core.stopSequenceAcquisition()

    assert shutter.close_count == 1
    assert not shutter._is_open


def test_autoshutter_continuous_sequence_acquisition():
    """Continuous acquisition should open shutter on start, close on stop."""
    core, shutter = _make_core("py", "py")
    assert shutter is not None

    core.startContinuousSequenceAcquisition()
    assert shutter.open_count == 1
    assert shutter._is_open

    while core.getRemainingImageCount() < 2:
        time.sleep(0.001)
    core.stopSequenceAcquisition()

    assert shutter.close_count == 1
    assert not shutter._is_open


def test_autoshutter_off_sequence_does_not_touch_shutter():
    """Sequence acquisition should not touch shutter when autoShutter is off."""
    core, shutter = _make_core("py", "py")
    assert shutter is not None
    core.setAutoShutter(False)

    core.startSequenceAcquisition(3, 0, True)
    while core.isSequenceRunning():
        time.sleep(0.001)
    core.stopSequenceAcquisition()

    assert shutter.open_count == 0
    assert shutter.close_count == 0
