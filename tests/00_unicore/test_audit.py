"""Regression tests from the review of UniMMCore on the pymmcore-nano bridge.

Each test documents a behavior found to be incorrect or inconsistent with the
C++ MMCore/MMDevice semantics during review, and failed before the fixes.
"""

from __future__ import annotations

import enum
import time
import types
from typing import TYPE_CHECKING
from unittest.mock import Mock

import numpy as np
import pytest

from pymmcore_plus import DeviceType
from pymmcore_plus.experimental.unicore import (
    CameraDevice,
    GenericDevice,
    HubDevice,
    SimpleCameraDevice,
    UniMMCore,
    XYStepperStageDevice,
)
from pymmcore_plus.experimental.unicore.devices._properties import pymm_property

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


# ---------------------------------------------------------------------------
# 1. Color cameras: CameraDevice.get_bytes_per_pixel() returned the dtype
#    itemsize, ignoring components.  MM::Camera::GetImageBytesPerPixel() is the
#    *total* bytes per pixel (RGB32 cameras report 4, with 4 components), and
#    MMCore sizes every copy with GetImageBufferSize() == w*h*bytesPerPixel.
#    A (h, w, 3) uint8 camera therefore reports 1 byte/pixel: CMMCore copies
#    one third of the frame, getImage() returns a (h, w) gray image of
#    interleaved channel bytes, and sequence frames are tagged GRAY8.
#    (The pre-PR pure-Python UniMMCore returned the (h, w, 3) array intact.)
# ---------------------------------------------------------------------------


class ColorCam(SimpleCameraDevice):
    def get_exposure(self) -> float:
        return 10.0

    def set_exposure(self, v: float) -> None:
        pass

    def sensor_shape(self) -> tuple[int, int, int]:
        return (16, 16, 3)

    def dtype(self):
        return np.uint8

    def snap(self, buffer: np.ndarray) -> Mapping:
        buffer[..., 0] = 10
        buffer[..., 1] = 20
        buffer[..., 2] = 30
        return {}


def test_color_camera_frame_is_not_truncated() -> None:
    core = UniMMCore()
    core.loadPyDevice("Cam", ColorCam())
    core.initializeDevice("Cam")
    core.setCameraDevice("Cam")
    assert core.getImageBufferSize() >= 16 * 16 * 3
    core.snapImage()
    img = core.getImage()
    assert img.shape == (16, 16, 3)
    np.testing.assert_array_equal(img[..., 0], 10)
    np.testing.assert_array_equal(img[..., 1], 20)
    np.testing.assert_array_equal(img[..., 2], 30)

    # sequence frames go through the circular buffer with the full pixel size
    core.startSequenceAcquisition(2, 0, True)
    while core.isSequenceRunning():
        pass
    frame = core.popNextImage()
    assert frame.shape == (16, 16, 3)
    np.testing.assert_array_equal(frame[..., 2], 30)


# ---------------------------------------------------------------------------
# 2. Devices loaded through a registered Python adapter are instantiated by the
#    C++ bridge (PyBridgeAdapter::CreateDevice -> cls()).  Nothing told the
#    Python object its label: Device._label_ stayed "" and UniMMCore._pydevices
#    did not know about it, so get_label() was wrong, isPyDevice() was False,
#    setProperty() skipped Python-side validation, and getSLMImage() refused it.
# ---------------------------------------------------------------------------


class LabelReporter(GenericDevice):
    """Device exposing its own label as a property."""

    @pymm_property(is_read_only=True)
    def my_label(self) -> str:
        return self.get_label()


def test_adapter_loaded_device_knows_its_label() -> None:
    mod = types.ModuleType("fake_adapter_mod")
    mod.__pymmcore_devices__ = [LabelReporter]  # type: ignore[attr-defined]
    core = UniMMCore()
    core.register_py_adapter("FakeAdapter", mod)
    core.loadDevice("LD", "FakeAdapter", "LabelReporter")
    assert core.isPyDevice("LD")
    core.initializeDevice("LD")
    assert core.getProperty("LD", "my_label") == "LD"
    # Python-side validation applies to adapter-loaded devices too
    with pytest.raises(ValueError, match="read-only"):
        core.setProperty("LD", "my_label", "x")
    core.unloadDevice("LD")
    assert not core.isPyDevice("LD")


# ---------------------------------------------------------------------------
# 3. XYStepperStageDevice did not implement set_x_origin / set_y_origin, which
#    pymmcore_nano.protocols.PyXYStepperStage requires.  core.setOriginX()
#    failed with an AttributeError instead of a device error.
# ---------------------------------------------------------------------------


class Stepper(XYStepperStageDevice):
    _x = _y = 0

    def set_position_steps(self, x: int, y: int) -> None:
        self._x, self._y = x, y

    def get_position_steps(self) -> tuple[int, int]:
        return (self._x, self._y)

    def get_step_size_x_um(self) -> float:
        return 0.1

    def get_step_size_y_um(self) -> float:
        return 0.1

    def home(self) -> None:
        pass

    def stop(self) -> None:
        pass


def test_stepper_satisfies_bridge_protocol() -> None:
    from pymmcore_nano.protocols import PyXYStepperStage

    assert isinstance(Stepper(), PyXYStepperStage)


def test_stepper_set_origin_x_does_not_raise_attribute_error() -> None:
    core = UniMMCore()
    core.loadPyDevice("XY", Stepper())
    core.initializeDevice("XY")
    core.setXYStageDevice("XY")
    with pytest.raises(RuntimeError) as ei:
        core.setOriginX("XY")
    assert "AttributeError" not in str(ei.value)


# ===========================================================================
# Review round 2 (nano-unicore-fixes2)
# ===========================================================================


class SeqCam(SimpleCameraDevice):
    def get_exposure(self) -> float:
        return 1.0

    def set_exposure(self, v: float) -> None:
        pass

    def sensor_shape(self) -> tuple[int, int]:
        return (8, 8)

    def dtype(self):
        return np.uint16

    def snap(self, buffer: np.ndarray) -> Mapping:
        buffer[:] = 7
        return {}


def _wait_sequence_done(core: UniMMCore, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while core.isSequenceRunning() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not core.isSequenceRunning()


# ---------------------------------------------------------------------------
# 4. After a sequence acquisition, CameraDevice.shutdown() ->
#    stop_sequence_acquisition() -> notify.acq_finished() raised (the bridge had
#    already invalidated notify), so unloadDevice() failed with "Device has
#    been unloaded", the device stayed loaded, and destroying the core
#    terminated the process.  The acquisition thread's `finally` also called
#    acq_finished() after unload.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("how", ["unloadDevice", "unloadAllDevices", "reset"])
@pytest.mark.parametrize("running", [False, True])
def test_unload_camera_after_sequence(how: str, running: bool) -> None:
    core = UniMMCore()
    core.loadPyDevice("Cam", SeqCam())
    core.initializeDevice("Cam")
    core.setCameraDevice("Cam")
    if running:
        core.startContinuousSequenceAcquisition(0)
        time.sleep(0.05)
        assert core.isSequenceRunning()
    else:
        core.startSequenceAcquisition(3, 0, True)
        _wait_sequence_done(core)
    if how == "unloadDevice":
        if running:
            # as for C++ cameras: CMMCore refuses to drop the camera role while
            # it is acquiring, and everything stays consistent
            with pytest.raises(RuntimeError, match="sequence acquisition"):
                core.unloadDevice("Cam")
            assert core.isPyDevice("Cam") and core.isSequenceRunning()
            core.stopSequenceAcquisition()
        core.unloadDevice("Cam")
    else:
        getattr(core, how)()  # stops a running acquisition first
    assert "Cam" not in core.getLoadedDevices()
    assert not core.isPyDevice("Cam")
    # no acquisition thread outlives the device
    time.sleep(0.1)
    del core


# ---------------------------------------------------------------------------
# 5. stop_sequence_acquisition() reported AcqFinished a second time (the
#    acquisition thread already reports it when it ends), so CMMCore emitted
#    sequenceAcquisitionStopped twice and closed the auto-shutter twice.
# ---------------------------------------------------------------------------


def test_acq_finished_reported_once_per_sequence() -> None:
    core = UniMMCore()
    cam = SeqCam()
    core.loadPyDevice("Cam", cam)
    core.initializeDevice("Cam")
    core.setCameraDevice("Cam")
    spy = Mock(wraps=cam._notify_)
    cam._notify_ = spy  # type: ignore[assignment]

    core.startContinuousSequenceAcquisition(0)
    time.sleep(0.05)
    core.stopSequenceAcquisition()
    time.sleep(0.1)
    assert spy.acq_finished.call_count == 1

    spy.acq_finished.reset_mock()
    core.startSequenceAcquisition(2, 0, True)
    _wait_sequence_done(core)
    core.stopSequenceAcquisition()  # already finished: nothing more to report
    assert spy.acq_finished.call_count == 1


# ---------------------------------------------------------------------------
# 6. The bridge calls get_image_buffer(channel) for core.getImage(channel);
#    CameraDevice.get_image_buffer() took no argument.
# ---------------------------------------------------------------------------


def test_get_image_with_channel_argument() -> None:
    core = UniMMCore()
    core.loadPyDevice("Cam", SeqCam())
    core.initializeDevice("Cam")
    core.setCameraDevice("Cam")
    core.snapImage()
    assert core.getImage(0).shape == (8, 8)


# ---------------------------------------------------------------------------
# 7. An unbounded acquisition is passed to start_sequence() as n=None.  The
#    bridge used to pass LONG_MAX (2**31-1 on Windows); it now passes None.
# ---------------------------------------------------------------------------


def test_continuous_acquisition_is_unbounded() -> None:
    seen: list = []

    class Cam(CameraDevice):
        def get_exposure(self) -> float:
            return 1.0

        def set_exposure(self, v: float) -> None:
            pass

        def shape(self) -> tuple[int, int]:
            return (4, 4)

        def dtype(self):
            return np.uint8

        def start_sequence(self, n, get_buffer):
            seen.append(n)
            return iter(())

    core = UniMMCore()
    core.loadPyDevice("Cam", Cam())
    core.initializeDevice("Cam")
    core.setCameraDevice("Cam")
    core.startContinuousSequenceAcquisition(0)
    _wait_sequence_done(core)
    core.startSequenceAcquisition(3, 0, True)
    _wait_sequence_done(core)
    assert seen == [None, 3]


# ---------------------------------------------------------------------------
# 8. Enum properties.  Every value crosses C++ as a string; the setter received
#    "Mode.B" (str() of the member) instead of Mode.B, and allowed values were
#    empty for a @pymm_property annotated with an Enum.  Enum members are
#    represented by their value on the C++ side (what a config file stores).
# ---------------------------------------------------------------------------


class Mode(enum.Enum):
    A = "a"
    B = "b"


class EnumDevice(GenericDevice):
    _mode = Mode.A

    @pymm_property
    def mode(self) -> Mode:
        return self._mode

    @mode.setter
    def _set_mode(self, v: Mode) -> None:
        assert isinstance(v, Mode), v
        self._mode = v


def test_enum_property_roundtrip(tmp_path: Path) -> None:
    core = UniMMCore()
    dev = EnumDevice()
    core.loadPyDevice("D", dev)
    core.initializeDevice("D")
    assert list(core.getAllowedPropertyValues("D", "mode")) == ["a", "b"]
    assert core.getProperty("D", "mode") == "a"

    core.setProperty("D", "mode", Mode.B)
    assert dev._mode is Mode.B
    core.setProperty("D", "mode", "a")
    assert dev._mode is Mode.A
    with pytest.raises((ValueError, RuntimeError)):
        core.setProperty("D", "mode", "c")

    core.defineConfig("G", "b", "D", "mode", Mode.B)
    core.setConfig("G", "b")
    assert dev._mode is Mode.B
    assert core.getCurrentConfig("G") == "b"

    cfg = tmp_path / "c.cfg"
    core.saveSystemConfiguration(cfg)
    assert "ConfigGroup,G,b,D,mode,b" in cfg.read_text()


def test_register_property_with_enum_type() -> None:
    class D(GenericDevice):
        def __init__(self) -> None:
            super().__init__()
            self.register_property("mode", default_value=Mode.A, property_type=Mode)

    core = UniMMCore()
    dev = D()
    core.loadPyDevice("D", dev)
    core.initializeDevice("D")
    assert list(core.getAllowedPropertyValues("D", "mode")) == ["a", "b"]
    core.setProperty("D", "mode", Mode.B)
    assert dev.get_property_value("mode") is Mode.B
    assert core.getProperty("D", "mode") == "b"


# ---------------------------------------------------------------------------
# 9. Pre-init properties did not exist before initializeDevice() (the bridge
#    registered everything in initialize_bridge) and could not be set after
#    it, so they were unusable and did not survive a config round trip.
# ---------------------------------------------------------------------------


class PortDevice(GenericDevice):
    port_at_init: str | None = None

    def __init__(self) -> None:
        super().__init__()
        self.register_property(
            "Port",
            default_value="COM1",
            is_pre_init=True,
            allowed_values=["COM1", "COM2"],
        )

    def initialize(self) -> None:
        self.port_at_init = self.get_property_value("Port")


def test_pre_init_property_set_before_initialize(tmp_path: Path) -> None:
    core = UniMMCore()
    dev = PortDevice()
    core.loadPyDevice("D", dev)
    assert core.isPropertyPreInit("D", "Port")
    core.setProperty("D", "Port", "COM2")
    core.initializeDevice("D")
    assert dev.port_at_init == "COM2"
    with pytest.raises(RuntimeError, match="pre-init"):
        core.setProperty("D", "Port", "COM1")

    cfg = tmp_path / "c.cfg"
    core.saveSystemConfiguration(cfg)
    core2 = UniMMCore()
    core2.loadSystemConfiguration(cfg)
    assert core2.getProperty("D", "Port") == "COM2"


# ---------------------------------------------------------------------------
# 10. Hubs.  (a) The Parent references of Python devices were not written to
#     config files.  (b) loadDevice(label, <hub module>, name) re-imported and
#     instantiated the class instead of loading the peripheral the hub reported
#     from detect_installed_devices(), so the hub's own instance was never
#     the one in the core, and classes not importable at module level could
#     not be peripherals at all.
# ---------------------------------------------------------------------------


class Motor(GenericDevice):
    """A motor on the hub."""

    def __init__(self, axis: str = "?") -> None:
        super().__init__()
        self.axis = axis


class MotorHub(HubDevice):
    """Controller with two motors."""

    def __init__(self) -> None:
        super().__init__()
        self.motor_x = Motor("x")

    def detect_installed_devices(self):
        return [
            ("MotorX", self.motor_x, DeviceType.Generic),
            ("MotorCls", Motor, DeviceType.Generic),
        ]


def test_hub_peripherals_and_config(tmp_path: Path) -> None:
    core = UniMMCore()
    hub = MotorHub()
    core.loadPyDevice("Hub", hub)
    core.initializeDevice("Hub")
    lib = core.getDeviceLibrary("Hub")
    assert set(core.getInstalledDevices("Hub")) == {"MotorX", "MotorCls"}

    core.loadDevice("X", lib, "MotorX")
    core.loadDevice("C", lib, "MotorCls")
    core.setParentLabel("X", "Hub")
    core.setParentLabel("C", "Hub")
    core.initializeDevice("X")
    core.initializeDevice("C")
    assert core.isPyDevice("X") and core.isPyDevice("C")
    # the instance reported by the hub is the one loaded, under its label
    assert core._pydevices["X"] is hub.motor_x
    assert hub.motor_x.get_label() == "X"
    assert isinstance(core._pydevices["C"], Motor)
    assert core.getDeviceLibrary("X") == lib
    # as in C++: the name the peripheral is loadable under, not the class name
    assert core.getDeviceName("C") == "MotorCls"
    assert set(core.getLoadedPeripheralDevices("Hub")) == {"X", "C"}

    cfg = tmp_path / "c.cfg"
    core.saveSystemConfiguration(cfg)
    text = cfg.read_text()
    assert "Parent,X,Hub" in text and "Parent,C,Hub" in text
    assert "_PyBridge_" not in text

    core2 = UniMMCore()
    core2.loadSystemConfiguration(cfg)
    assert set(core2.getLoadedDevices()) >= {"Hub", "X", "C"}
    assert core2.getParentLabel("X") == "Hub"
    assert core2._pydevices["X"] is core2._pydevices["Hub"].motor_x

    # unloading a peripheral keeps the hub, unloading the hub keeps peripherals
    core.unloadDevice("X")
    assert "Hub" in core.getLoadedDevices()
    core.unloadDevice("Hub")
    assert "C" in core.getLoadedDevices()
