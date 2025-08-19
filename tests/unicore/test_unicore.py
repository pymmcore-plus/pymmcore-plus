import weakref
from collections.abc import Sequence
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from pymmcore_plus import DeviceInitializationState, DeviceType, PropertyType, _pymmcore
from pymmcore_plus.experimental.unicore import GenericDevice, UniMMCore, pymm_property

DOC = """Example generic device."""
PROP_A = "propA"  # must match below
PROP_B = "propB"  # must match below
PROP_S = "propS"  # must match below
ERR = RuntimeError("Bad device")
PYDEV = "pyDev"
MAX_LEN = 4


class RandomClass: ...


class MyDevice(GenericDevice):
    @pymm_property
    def propA(self) -> str:
        """Some property."""
        return "hi"

    _prop_b = 10.0

    @pymm_property(limits=(0.0, 100.0))
    def propB(self) -> float:
        """Some other property."""
        return self._prop_b

    @propB.setter
    def _set_prop_b(self, value: int) -> None:
        self._prop_b = value

    _prop_s = 1
    _prop_s_seq: tuple[int, ...] = ()
    _prop_started = False
    _prop_stopped = False

    @pymm_property(allowed_values=[1, 2, 4, 8], sequence_max_length=MAX_LEN)
    def propS(self) -> int:
        """Some sequence property."""
        return self._prop_s

    @propS.setter
    def _set_prop_s(self, value: int) -> None:
        self._prop_s = value

    @propS.sequence_loader
    def _load_prop_s(self, sequence: Sequence[int]) -> None:
        self._prop_s_seq = tuple(sequence)

    @propS.sequence_starter
    def _start_prop_s(self) -> None:
        self._prop_started = True

    @propS.sequence_stopper
    def _stop_prop_s(self) -> None:
        self._prop_stopped = True


class BadDevice(GenericDevice):
    def initialize(self):
        raise ERR


MyDevice.__doc__ = DOC


def test_device_load_unload():
    core = UniMMCore()

    device = MyDevice()
    assert device.get_label() != PYDEV
    with pytest.raises(AttributeError):
        _ = device.core

    core.loadPyDevice(PYDEV, device)

    with pytest.raises(ValueError, match="already in use"):
        core.loadPyDevice(PYDEV, device)

    assert device.get_label() == PYDEV
    assert isinstance(device.core, ModuleType)  # proxy object

    assert PYDEV in core.getLoadedDevices()
    assert core.getDeviceLibrary(PYDEV) == __name__  # because it's in this module
    assert core.getDeviceName(PYDEV) == MyDevice.__name__
    assert core.getDeviceType(PYDEV) == DeviceType.GenericDevice
    assert core.getDeviceDescription(PYDEV) == DOC  # docstring

    assert (
        core.getDeviceInitializationState(PYDEV)
        is DeviceInitializationState.Uninitialized
    )
    core.initializeDevice(PYDEV)
    assert (
        core.getDeviceInitializationState(PYDEV)
        is DeviceInitializationState.InitializedSuccessfully
    )

    with pytest.raises(
        ValueError, match="wrong device type for the requested operation"
    ):
        core.setXYPosition(PYDEV, 1, 1)

    devref = weakref.ref(device)
    del device
    core.unloadDevice(PYDEV)
    assert PYDEV not in core.getLoadedDevices()
    assert devref() is None  # we hold no references to the device

    core.loadPyDevice(PYDEV, MyDevice())
    core.unloadAllDevices()
    assert PYDEV not in core.getLoadedDevices()


def test_reset():
    core = UniMMCore()
    core.loadSystemConfiguration()
    core.loadPyDevice(PYDEV, MyDevice())

    assert "Camera" in core.getLoadedDevices()
    assert PYDEV in core.getLoadedDevices()
    core.reset()
    assert "Camera" not in core.getLoadedDevices()
    assert PYDEV not in core.getLoadedDevices()


def test_failed_device_init():
    core = UniMMCore()

    core.loadDevice(PYDEV, __name__, BadDevice.__name__)
    assert PYDEV in core.getLoadedDevices()
    core.initializeAllDevices()
    assert (
        core.getDeviceInitializationState(PYDEV)
        is DeviceInitializationState.InitializationFailed
    )


def test_device_load_from_module():
    core = UniMMCore()

    core.loadDevice(PYDEV, __name__, MyDevice.__name__)
    assert PYDEV in core.getLoadedDevices()
    assert core.getDeviceLibrary(PYDEV) == __name__

    # If we gave a proper library name, but a bad device name...
    # it should raise the usual error
    msg = (
        "failed to instantiate device"
        if _pymmcore.version_info >= (11, 5)
        else "Failed to load device"
    )
    with pytest.raises(RuntimeError, match=msg):
        core.loadDevice("newdev", "DemoCamera", "NoSuchDevice")

    # Then we fallback to checking python modules
    # module doesn't exist:
    with pytest.raises(
        ImportError,
        match="not a known Micro-manager DeviceAdapter, or an importable python module",
    ):
        core.loadDevice("newdev", "no_such_module", "MyDevice")

    # module doesn't exist:
    with pytest.raises(AttributeError, match="Could not find class 'NoSuchDevice'"):
        core.loadDevice("newdev", __name__, "NoSuchDevice")

    # module doesn't exist:
    with pytest.raises(TypeError, match="not a subclass"):
        core.loadDevice("newdev", __name__, RandomClass.__name__)


def test_waiting():
    core = UniMMCore()

    core.loadPyDevice(PYDEV, MyDevice())
    core.initializeDevice(PYDEV)

    assert not core.deviceBusy(PYDEV)
    core.waitForDevice(PYDEV)
    core.waitForSystem()

    assert not core.deviceTypeBusy(DeviceType.Any)
    assert not core.systemBusy()

    core.setTimeoutMs(1000)
    pydev_mock = MagicMock(wraps=core._pydevices)
    core._pydevices = pydev_mock
    core.waitForSystem()
    pydev_mock.wait_for_device_type.assert_called_once_with(DeviceType.Any, 1000)


def test_unicore_props():
    core = UniMMCore()

    core.load_py_device(PYDEV, MyDevice())
    core.initializeDevice(PYDEV)

    assert PROP_A in core.getDevicePropertyNames(PYDEV)
    assert core.hasProperty(PYDEV, PROP_A)
    assert core.isPropertyPreInit(PYDEV, PROP_A) is False
    assert core.isPropertyReadOnly(PYDEV, PROP_A) is True
    assert core.isPropertyReadOnly(PYDEV, PROP_B) is False
    assert core.hasPropertyLimits(PYDEV, PROP_B)
    assert not core.hasPropertyLimits(PYDEV, PROP_A)
    assert core.getPropertyLowerLimit(PYDEV, PROP_B) == 0.0
    assert core.getPropertyUpperLimit(PYDEV, PROP_B) == 100.0
    assert core.getPropertyType(PYDEV, PROP_A) == PropertyType.String
    assert core.getPropertyType(PYDEV, PROP_B) == PropertyType.Float

    assert core.getProperty(PYDEV, PROP_A) == "hi"
    assert core.getPropertyFromCache(PYDEV, PROP_A) == "hi"
    with pytest.raises(KeyError, match="not found in cache"):
        core.getPropertyFromCache(PYDEV, PROP_B)

    with pytest.raises(ValueError, match="Property 'propA' is read-only"):
        core.setProperty(PYDEV, PROP_A, 50.0)

    core.setProperty(PYDEV, PROP_B, 50)
    assert core.getProperty(PYDEV, PROP_B) == 50.0

    with pytest.raises(ValueError, match="not within the allowed range"):
        core.setProperty(PYDEV, PROP_B, 101.0)

    with pytest.raises(ValueError, match="Non-numeric value"):
        core.setProperty(PYDEV, PROP_B, "bad")


def test_property_sequences():
    core = UniMMCore()

    dev = MyDevice()
    core.loadPyDevice(PYDEV, dev)
    core.initializeDevice(PYDEV)

    assert not core.isPropertySequenceable(PYDEV, PROP_A)
    assert core.isPropertySequenceable(PYDEV, PROP_S)
    assert core.getPropertySequenceMaxLength(PYDEV, PROP_S) == MAX_LEN

    with pytest.raises(RuntimeError, match="'propA' is not sequenceable"):
        core.loadPropertySequence(PYDEV, PROP_A, [1, 2, 3])
    with pytest.raises(RuntimeError, match="'propA' is not sequenceable"):
        core.startPropertySequence(PYDEV, PROP_A)

    with pytest.raises(ValueError, match="Value '3' is not allowed"):
        core.loadPropertySequence(PYDEV, PROP_S, [1, 2, 3])

    with pytest.raises(ValueError, match="20 exceeds the maximum allowed"):
        core.loadPropertySequence(PYDEV, PROP_S, [1, 2] * 10)

    core.loadPropertySequence(PYDEV, PROP_S, [1, 2, 4])
    assert dev._prop_s_seq == (1, 2, 4)

    core.startPropertySequence(PYDEV, PROP_S)
    assert dev._prop_started

    core.stopPropertySequence(PYDEV, PROP_S)
    assert dev._prop_stopped


def test_device_can_update_props():
    core = UniMMCore()
    dev = MyDevice()
    core.loadPyDevice(PYDEV, dev)
    core.initializeDevice(PYDEV)

    with pytest.raises(ValueError, match="20 exceeds the maximum allowed"):
        core.loadPropertySequence(PYDEV, PROP_S, [1, 2] * 10)

    dev.set_property_sequence_max_length(PROP_S, 20)
    core.loadPropertySequence(PYDEV, PROP_S, [1, 2] * 10)
    assert dev._prop_s_seq == (1, 2) * 10

    with pytest.raises(ValueError, match="not within the allowed range"):
        core.setProperty(PYDEV, PROP_B, 200)
    dev.set_property_limits(PROP_B, (0.0, 200.0))
    core.setProperty(PYDEV, PROP_B, 200)

    with pytest.raises(ValueError, match="Value '3' is not allowed"):
        core.loadPropertySequence(PYDEV, PROP_S, [1, 2, 3])

    dev.set_property_allowed_values(PROP_S, [1, 2, 3])
    core.loadPropertySequence(PYDEV, PROP_S, [1, 2, 3])
