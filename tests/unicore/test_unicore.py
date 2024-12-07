import weakref
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from pymmcore_plus import DeviceInitializationState, DeviceType, PropertyType
from pymmcore_plus.experimental.unicore import Device, UniMMCore, pymm_property

DOC = """Example generic device."""
PROP_NAME = "propA"  # must match below
ERR = RuntimeError("Bad device")
PYDEV = "pyDev"


class RandomClass: ...


class MyDevice(Device):
    @pymm_property(limits=(0.0, 100.0))
    def propA(self) -> float:
        """Some property."""
        return 1


class BadDevice(Device):
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
    assert core.getDeviceType(PYDEV) == DeviceType.Unknown
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
    with pytest.raises(RuntimeError, match="Failed to load device"):
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
    core.setTimeoutMs(1000)
    pydev_mock = MagicMock(wraps=core._pydevices)
    core._pydevices = pydev_mock
    core.waitForSystem()
    pydev_mock.wait_for_device_type.assert_called_once_with(DeviceType.Any, 1000)


def test_unicore_props():
    core = UniMMCore()

    core.load_py_device(PYDEV, MyDevice())
    core.initializeDevice(PYDEV)

    assert PROP_NAME in core.getDevicePropertyNames(PYDEV)
    assert core.hasProperty(PYDEV, PROP_NAME)
    assert core.isPropertyPreInit(PYDEV, PROP_NAME) is False
    assert core.isPropertyReadOnly(PYDEV, PROP_NAME) is False
    assert core.hasPropertyLimits(PYDEV, PROP_NAME)
    assert core.getPropertyLowerLimit(PYDEV, PROP_NAME) == 0.0
    assert core.getPropertyUpperLimit(PYDEV, PROP_NAME) == 100.0
    assert core.getPropertyType(PYDEV, PROP_NAME) == PropertyType.Float
    assert core.getProperty(PYDEV, PROP_NAME) == 1.0
    assert core.getPropertyFromCache(PYDEV, PROP_NAME) == 1.0

    assert not core.deviceBusy(PYDEV)
    core.waitForDevice(PYDEV)
