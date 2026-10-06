"""Regression tests from the review of UniMMCore on the pymmcore-nano bridge.

Each test documents a behavior found to be incorrect or inconsistent with the
C++ MMCore/MMDevice semantics during review, and failed before the fixes.
"""

from __future__ import annotations

import enum
import sys
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
    StageDevice,
    StateDevice,
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


class FailingShutdownCam(SeqCam):
    calls = 0

    def shutdown(self) -> None:
        self.calls += 1
        raise RuntimeError("controller unreachable")


def test_error_in_shutdown_is_reported_once() -> None:
    """As for a C++ device whose Shutdown() fails: the unload raises and the
    device stays loaded (and tracked); the next unload succeeds without
    calling shutdown() again, and destroying the core does not abort."""
    core = UniMMCore()
    cam = FailingShutdownCam()
    core.loadPyDevice("Cam", cam)
    core.initializeDevice("Cam")
    with pytest.raises(RuntimeError, match="controller unreachable"):
        core.unloadDevice("Cam")
    assert core.isPyDevice("Cam") and "Cam" in core.getLoadedDevices()
    core.unloadDevice("Cam")
    assert not core.isPyDevice("Cam") and cam.calls == 1
    core.loadPyDevice("Cam2", FailingShutdownCam())
    core.initializeDevice("Cam2")
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
    # a reported class is instantiated as-is (not through a tracking subclass)
    assert type(core._pydevices["C"]) is Motor
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


# ---------------------------------------------------------------------------
# 11. setProperty() rejected string values for numeric properties with allowed
#     values, and passed non-numeric strings for Float properties through.
#
#     PropertyController.validate() compared the raw value against
#     allowed_values without coercing it to the property type.  StateDevice
#     registers "State" as an Integer property with allowed values (0, 1, ...),
#     so setProperty(dev, "State", "2") -- the form pymmcore's API takes, that
#     configuration files produce and that property widgets send -- raised
#     ValueError while the int 2 worked.  For a Float property without limits,
#     "abc" went to C++, where MM::FloatProperty::Set() turns it into 0.0.
# ---------------------------------------------------------------------------


class _Wheel(StateDevice):
    _pos = 0

    def __init__(self) -> None:
        super().__init__({0: "a", 1: "b", 2: "c"})

    def get_state(self) -> int:
        return self._pos

    def set_state(self, p: int) -> None:
        self._pos = p


class _ZStage(StageDevice):
    """A Z stage."""

    _p = 0.0

    def set_position_um(self, v: float) -> None:
        self._p = v

    def get_position_um(self) -> float:
        return self._p

    def home(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def set_origin(self) -> None:
        pass


@pytest.fixture
def fake_module() -> types.ModuleType:
    """An importable module providing _Wheel and _ZStage (for config files)."""
    mod = types.ModuleType("_audit_fake_adapter")
    mod._Wheel = _Wheel  # type: ignore[attr-defined]
    mod._ZStage = _ZStage  # type: ignore[attr-defined]
    mod.__pymmcore_devices__ = [_Wheel, _ZStage]  # type: ignore[attr-defined]
    sys.modules[mod.__name__] = mod
    try:
        yield mod
    finally:
        sys.modules.pop(mod.__name__, None)


def test_set_property_accepts_strings_for_numeric_properties() -> None:
    core = UniMMCore()
    core.loadPyDevice("W", _Wheel())
    core.initializeDevice("W")
    core.setProperty("W", "State", "2")
    assert core.getState("W") == 2
    core.setProperty("W", "State", 1)
    assert core.getState("W") == 1
    with pytest.raises(ValueError, match="not allowed"):
        core.setProperty("W", "State", "7")
    with pytest.raises(ValueError, match="not a valid Integer"):
        core.setProperty("W", "State", "two")


def test_config_file_can_set_state_property(
    tmp_path: Path, fake_module: types.ModuleType
) -> None:
    cfg = tmp_path / "wheel.cfg"
    cfg.write_text(
        f"#py Device,W,{fake_module.__name__},_Wheel\n"
        "Property,Core,Initialize,1\n"
        "Property,W,State,2\n"
    )
    core = UniMMCore()
    core.loadSystemConfiguration(cfg)
    assert core.getState("W") == 2


class _Gain(GenericDevice):
    _g = 1.0

    @pymm_property
    def gain(self) -> float:
        return self._g

    @gain.setter
    def gain(self, v: float) -> None:
        self._g = v


def test_non_numeric_value_for_float_property_is_rejected() -> None:
    core = UniMMCore()
    dev = _Gain()
    core.loadPyDevice("G", dev)
    core.initializeDevice("G")
    with pytest.raises(ValueError, match="not a valid Float"):
        core.setProperty("G", "gain", "abc")
    assert dev._g == 1.0
    core.setProperty("G", "gain", "2.5")
    assert dev._g == 2.5


# ---------------------------------------------------------------------------
# 12. Only the first device loaded from a registered Python adapter was
#     tracked.  register_py_adapter() handed the adapter factories
#     `self._pending_pydevices.append`, and _adopt_bridge_created() replaced
#     that list with a new one, so later factory calls appended to an orphaned
#     list and the devices were never adopted (isPyDevice() False).
# ---------------------------------------------------------------------------


def test_every_device_from_a_registered_adapter_is_tracked(
    fake_module: types.ModuleType,
) -> None:
    core = UniMMCore()
    core.register_py_adapter("AuditAdapter", fake_module)
    for label in ("Z1", "Z2", "Z3"):
        core.loadDevice(label, "AuditAdapter", "_ZStage")
    core.initializeAllDevices()
    assert all(core.isPyDevice(lbl) for lbl in ("Z1", "Z2", "Z3"))
    assert len({id(core._pydevices[lbl]) for lbl in ("Z1", "Z2", "Z3")}) == 3
    assert core.getDeviceDescription("Z2") == "A Z stage."


# ---------------------------------------------------------------------------
# 13. getCurrentConfigFromCache() queried the hardware.  When CMMCore's string
#     comparison found no preset (cache "3.0000" vs preset "3.0"), the fallback
#     read every setting with getProperty(), a device call.  The FromCache
#     variant exists so that GUIs and the MDA engine can poll it without
#     touching devices.
# ---------------------------------------------------------------------------


class _Polled(GenericDevice):
    reads = 0
    _v = 3.0

    @pymm_property
    def polled(self) -> float:
        type(self).reads += 1
        return self._v

    @polled.setter
    def polled(self, v: float) -> None:
        self._v = v


def test_get_current_config_from_cache_does_not_query_the_device() -> None:
    core = UniMMCore()
    core.loadPyDevice("P", _Polled())
    core.initializeDevice("P")
    core.defineConfig("grp", "p1", "P", "polled", "3.0")
    core.defineConfig("grp", "p2", "P", "polled", "4.0")
    core.setProperty("P", "polled", 3)  # the cache holds "3.0000"
    assert super(UniMMCore, core).getCurrentConfigFromCache("grp") == ""
    reads = _Polled.reads
    assert core.getCurrentConfigFromCache("grp") == "p1"
    assert _Polled.reads == reads, "getCurrentConfigFromCache read the device"
    assert core.getCurrentConfig("grp") == "p1"  # this one may read the device


# ---------------------------------------------------------------------------
# 14. A hub peripheral reported as a zero-argument *function* (allowed by the
#     pymmcore-nano PyHub protocol) was tracked as the function: the tracker
#     only special-cased classes, so the function ended up in _pydevices and
#     getDeviceDescription() raised AttributeError.
# ---------------------------------------------------------------------------


def test_hub_function_factory_peripheral_is_tracked_as_a_device() -> None:
    class Hub(HubDevice):
        def detect_installed_devices(self):
            return [("Z", lambda: _ZStage(), DeviceType.Stage)]

    core = UniMMCore()
    core.loadPyDevice("H", Hub())
    core.initializeDevice("H")
    core.loadDevice("Z", core.getDeviceLibrary("H"), "Z")
    core.initializeDevice("Z")
    assert core.isPyDevice("Z")
    assert isinstance(core._pydevices["Z"], _ZStage)
    assert core.getDeviceDescription("Z") == "A Z stage."


# ---------------------------------------------------------------------------
# 15. Decorated (@pymm_property) properties shared one PropertyInfo between
#     all instances of a class: set_property_limits() on one device changed
#     get_property_info().limits and the Python-side validation of every other
#     device of that class, while CMMCore's limits stayed per device.
# ---------------------------------------------------------------------------


class _Limited(GenericDevice):
    _v = 1.0

    @pymm_property(limits=(0, 10))
    def lim(self) -> float:
        return self._v

    @lim.setter
    def lim(self, v: float) -> None:
        self._v = v


def test_property_info_is_per_instance() -> None:
    core = UniMMCore()
    d1, d2 = _Limited(), _Limited()
    core.loadPyDevice("D1", d1)
    core.loadPyDevice("D2", d2)
    core.initializeAllDevices()
    d1.set_property_limits("lim", (0, 100))
    assert d1.get_property_info("lim").limits == (0, 100)
    assert d2.get_property_info("lim").limits == (0, 10)
    assert core.getPropertyUpperLimit("D1", "lim") == 100
    assert core.getPropertyUpperLimit("D2", "lim") == 10
    core.setProperty("D1", "lim", 50)
    with pytest.raises(ValueError, match="not within"):
        core.setProperty("D2", "lim", 50)
    # attribute access goes through the instance's own controller too
    d1.lim = 60
    with pytest.raises(ValueError, match="not within"):
        d2.lim = 60
    assert (d1.lim, d2.lim) == (60, 1.0)
    assert d1.get_property_info("lim").last_value == 60
    assert d2.get_property_info("lim").last_value == 1.0


# ---------------------------------------------------------------------------
# 16. A subclass redefining a @pymm_property got the base class's controller:
#     __init_subclass__ walked the MRO from the most derived class to the base,
#     so the base's definition overwrote the subclass's.
# ---------------------------------------------------------------------------


def test_subclass_property_overrides_base_property() -> None:
    class Base(GenericDevice):
        @pymm_property
        def gain(self) -> float:
            return 1.0

    class Derived(Base):
        @pymm_property(limits=(0, 5))
        def gain(self) -> float:
            return 2.0

    dev = Derived()
    assert dev.get_property_value("gain") == 2.0
    assert dev.get_property_info("gain").limits == (0, 5)
    core = UniMMCore()
    core.loadPyDevice("D", dev)
    core.initializeDevice("D")
    assert core.getProperty("D", "gain") == "2.0000"
    assert core.getPropertyUpperLimit("D", "gain") == 5


# ---------------------------------------------------------------------------
# 17. set_property_limits() updated the Python-side info before asking the
#     core, which (since pymmcore-nano reports CDeviceBase's error codes)
#     rejects limits on a String property: the device would then believe in a
#     constraint the core does not enforce.
# ---------------------------------------------------------------------------


def test_rejected_limits_leave_python_info_unchanged() -> None:
    class Dev(GenericDevice):
        @pymm_property
        def mode(self) -> str:
            return "a"

        @mode.setter
        def mode(self, v: str) -> None:
            pass

    core = UniMMCore()
    dev = Dev()
    core.loadPyDevice("D", dev)
    core.initializeDevice("D")
    with pytest.raises(RuntimeError, match="Cannot set limits"):
        dev.set_property_limits("mode", (0, 5))
    assert dev.get_property_info("mode").limits is None
    assert not core.hasPropertyLimits("D", "mode")
