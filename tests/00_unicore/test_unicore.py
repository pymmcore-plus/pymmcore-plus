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


def test_waiting():
    core = UniMMCore()

    core.loadPyDevice(PYDEV, MyDevice())
    core.initializeDevice(PYDEV)

    assert not core.deviceBusy(PYDEV)
    core.waitForDevice(PYDEV)
    core.waitForSystem()

    assert not core.deviceTypeBusy(DeviceType.Any)
    assert not core.systemBusy()

    core.setTimeoutMs(500)
    pydev_mock = MagicMock(wraps=core._pydevices)
    core._pydevices = pydev_mock
    core.waitForSystem()
    pydev_mock.wait_for_device_type.assert_called_once_with(DeviceType.Any, 500)


def test_define_config_groups():
    core = UniMMCore()

    # Note: C++ is permissive with names - only validates certain characters
    # e.g., commas in preset names are forbidden but empty names are allowed
    core.defineConfigGroup("group1")
    assert core.isGroupDefined("group1")
    assert tuple(core.getAvailableConfigGroups()) == ("group1",)
    with pytest.raises((RuntimeError, ValueError), match="already in use"):
        core.defineConfigGroup("group1")

    core.defineConfig("group1", "preset1")

    core.renameConfigGroup("group1", "renamed_group")
    assert core.isGroupDefined("renamed_group")
    assert not core.isGroupDefined("group1")

    with pytest.raises((ValueError, RuntimeError), match="not defined"):
        core.renameConfigGroup("group1", "another_name")

    # rename Config
    with pytest.raises((ValueError, RuntimeError), match="does not exist"):
        core.renameConfig("notagroup", "nonexistent_preset", "new_name")
    with pytest.raises((ValueError, RuntimeError), match="does not exist"):
        core.renameConfig("renamed_group", "nonexistent_preset", "new_name")

    core.renameConfig("renamed_group", "preset1", "renamed_preset")
    assert core.isConfigDefined("renamed_group", "renamed_preset")

    # Cleanup
    core.deleteConfigGroup("renamed_group")
    assert not core.isGroupDefined("renamed_group")

    with pytest.raises((ValueError, RuntimeError), match="not defined"):
        core.deleteConfigGroup("renamed_group")

    assert tuple(core.getAvailableConfigGroups()) == ()


def test_config_group_with_c_and_py_devices():
    core = UniMMCore()

    core.defineConfigGroup("group1")
    core.loadDevice("CDev", "DemoCamera", "DCam")
    core.loadPyDevice("PyDev", MyDevice())
    core.initializeAllDevices()
    core.setCameraDevice("CDev")

    # Note: C++ validation is permissive - it only validates certain characters
    # (like commas) and doesn't strictly validate empty strings or None values

    core.defineConfig("group1", "preset1", "CDev", "Exposure", 50)
    core.defineConfig("group1", "preset1", "PyDev", "propB", 25.0)
    assert core.isConfigDefined("group1", "preset1")
    core.defineConfig("group1", "preset2", "CDev", "Exposure", 150)
    core.defineConfig("group1", "preset2", "PyDev", "propB", 125.0)
    assert tuple(core.getAvailableConfigs("group1")) == ("preset1", "preset2")

    # Get the config data (stored values)
    config = core.getConfigData("group1", "preset1")
    assert list(config) == [("CDev", "Exposure", "50"), ("PyDev", "propB", "25.0")]

    # Before applying the config, current values differ from stored values
    cfg_state_before = core.getConfigState("group1", "preset1")
    assert cfg_state_before != config  # Current state differs from stored config

    with pytest.raises((ValueError, RuntimeError), match="does not exist"):
        core.getConfigData("group1", "preset3")

    with pytest.raises((ValueError, RuntimeError), match="does not exist"):
        core.getConfigState("group10", "preset3")
    with pytest.raises((ValueError, RuntimeError), match="does not exist"):
        core.getConfigState("group1", "preset31")

    assert core.getCurrentConfig("group1") == ""

    # Apply the config and check core values
    assert core.getExposure() != 50
    assert core.getProperty("PyDev", "propB") != 25.0
    core.setConfig("group1", "preset1")
    assert core.getExposure() == 50
    assert core.getProperty("PyDev", "propB") == 25.0

    # After applying config, getConfigState should return values matching current state
    cfg_state_after = core.getConfigState("group1", "preset1")
    # The values should now match (though format may differ, e.g., "50.0000" vs "50")
    assert list(cfg_state_after) == [
        ("CDev", "Exposure", "50.0000"),
        ("PyDev", "propB", "25.0"),
    ]

    cfg_group_state = core.getConfigGroupState("group1")
    cfg_group_state_cached = core.getConfigGroupStateFromCache("group1")
    assert (
        list(cfg_group_state)
        == list(cfg_group_state_cached)
        == [
            ("CDev", "Exposure", "50.0000"),
            ("PyDev", "propB", "25.0"),
        ]
    )

    assert core.getCurrentConfig("group1") == "preset1"
    assert core.getCurrentConfigFromCache("group1") == "preset1"

    with pytest.raises((ValueError, RuntimeError), match="does not exist"):
        core.setConfig("group10", "preset3")
    with pytest.raises((ValueError, RuntimeError), match="does not exist"):
        core.setConfig("group1", "preset10")

    # Clean up
    with pytest.raises(RuntimeError, match="not found in device"):
        core.deleteConfig("group1", "preset1", "CDev", "NotExposure")

    core.deleteConfig("group1", "preset1", "CDev", "Exposure")
    config = core.getConfigData("group1", "preset1")
    assert list(config) == [("PyDev", "propB", "25.0")]

    with pytest.raises((ValueError, RuntimeError), match="does not exist"):
        core.deleteConfig("group3", "preset1")

    core.deleteConfig("group1", "preset1")
    with pytest.raises((ValueError, RuntimeError), match="does not exist"):
        core.getConfigData("group1", "preset1")
    with pytest.raises((ValueError, RuntimeError), match="does not exist"):
        core.deleteConfig("group1", "preset1")

    core.deleteConfigGroup("group1")
    with pytest.raises((ValueError, RuntimeError), match="does not exist"):
        core.getConfigData("group1", "preset1")


def test_config_group_channel_groups():
    core = UniMMCore()

    core.defineConfigGroup("channel")
    core.defineConfig("channel", "preset1")
    core.defineConfig("channel", "preset2")

    # C++ raises ValueError for invalid channel group
    with pytest.raises((RuntimeError, ValueError)):
        core.setChannelGroup("nonexistent_group")

    # Test channelGroupChanged event
    channel_group_changed_mock = MagicMock()
    core.events.channelGroupChanged.connect(channel_group_changed_mock)

    assert not core.getChannelGroup()
    core.setChannelGroup("channel")
    assert core.getChannelGroup() == "channel"
    channel_group_changed_mock.assert_called_with("channel")

    # Setting same group again should not emit event
    channel_group_changed_mock.reset_mock()
    core.setChannelGroup("channel")
    channel_group_changed_mock.assert_not_called()

    core.deleteConfigGroup("channel")
    assert not core.getChannelGroup()


def test_config_group_events():
    """Test that config group operations emit the correct events."""

    core = UniMMCore()

    # Load a real device so we can set valid properties
    core.loadDevice("Cam", "DemoCamera", "DCam")
    core.initializeAllDevices()

    # Set up mock listeners
    config_defined_mock = MagicMock()
    config_set_mock = MagicMock()
    config_deleted_mock = MagicMock()
    config_group_deleted_mock = MagicMock()

    core.events.configDefined.connect(config_defined_mock)
    core.events.configSet.connect(config_set_mock)
    core.events.configDeleted.connect(config_deleted_mock)
    core.events.configGroupDeleted.connect(config_group_deleted_mock)

    # Test defineConfig event - creates group implicitly
    core.defineConfig("testGroup", "preset1", "Cam", "Exposure", "50")
    config_defined_mock.assert_called_once_with(
        "testGroup", "preset1", "Cam", "Exposure", "50"
    )
    config_defined_mock.reset_mock()

    # Test defineConfig event - empty preset (no device/prop/value)
    core.defineConfig("testGroup", "preset2")
    config_defined_mock.assert_called_once_with("testGroup", "preset2", "", "", "")
    config_defined_mock.reset_mock()

    # Test setConfig event
    core.setConfig("testGroup", "preset1")
    config_set_mock.assert_called_once_with("testGroup", "preset1")
    assert core._last_config == ("testGroup", "preset1")

    # Test deleteConfig event (delete property from preset)
    core.deleteConfig("testGroup", "preset1", "Cam", "Exposure")
    config_deleted_mock.assert_called_once_with("testGroup", "preset1")
    config_deleted_mock.reset_mock()

    # Test deleteConfig event (delete entire preset)
    core.deleteConfig("testGroup", "preset2")
    config_deleted_mock.assert_called_once_with("testGroup", "preset2")
    config_deleted_mock.reset_mock()

    # Test deleteConfigGroup event
    core.deleteConfigGroup("testGroup")
    config_group_deleted_mock.assert_called_once_with("testGroup")


def test_wait_for_config():
    """Test waitForConfig blocks until all devices in a config are ready."""
    core = UniMMCore()

    # Load both C++ and Python devices
    core.loadDevice("CDev", "DemoCamera", "DCam")
    core.loadPyDevice("PyDev", MyDevice())
    core.initializeAllDevices()

    # Create a config with both device types
    core.defineConfigGroup("testGroup")
    core.defineConfig("testGroup", "preset1", "CDev", "Exposure", "50")
    core.defineConfig("testGroup", "preset1", "PyDev", "propB", "25.0")

    # waitForConfig should work without raising
    core.waitForConfig("testGroup", "preset1")

    # Should raise for non-existent group/preset
    with pytest.raises((RuntimeError, ValueError)):
        core.waitForConfig("nonexistent", "preset1")

    with pytest.raises((RuntimeError, ValueError)):
        core.waitForConfig("testGroup", "nonexistent")


def test_system_state_includes_py_devices():
    """Test getSystemState and getSystemStateCache include Python device properties."""
    core = UniMMCore()

    # Load both C++ and Python devices
    core.loadDevice("CDev", "DemoCamera", "DCam")
    core.loadPyDevice("PyDev", MyDevice())
    core.initializeAllDevices()

    # Set a property value on Python device
    core.setProperty("PyDev", "propB", 42.0)

    # getSystemState should include Python device properties
    state = core.getSystemState()
    py_props = [(d, p, v) for d, p, v in state if d == "PyDev"]
    assert len(py_props) > 0, "Python device properties should be in system state"
    assert any(p == "propB" for _, p, _ in py_props), "propB should be in system state"

    # getSystemStateCache should also include Python device properties
    state_cache = core.getSystemStateCache()
    py_props_cache = [(d, p, v) for d, p, v in state_cache if d == "PyDev"]
    assert len(py_props_cache) > 0, "Python device properties should be in cache"

    # updateSystemStateCache should populate Python device cache
    core.updateSystemStateCache()
    state_after_update = core.getSystemStateCache()
    py_props_after = [(d, p, v) for d, p, v in state_after_update if d == "PyDev"]
    assert len(py_props_after) > 0

    # Native mode should return pymmcore.Configuration
    import pymmcore_plus._pymmcore as pymmcore

    native_state = core.getSystemState(native=True)
    assert isinstance(native_state, pymmcore.Configuration)


def test_delete_python_device_property_from_config():
    """Test deleting a specific Python device property from a config preset."""
    core = UniMMCore()

    # Load Python device
    core.loadPyDevice("PyDev", MyDevice())
    core.initializeAllDevices()

    # Create a config with multiple Python device properties
    core.defineConfigGroup("testGroup")
    core.defineConfig("testGroup", "preset1", "PyDev", "propA", "valueA")
    core.defineConfig("testGroup", "preset1", "PyDev", "propB", 42.0)

    # Verify both properties are in the config
    config = core.getConfigData("testGroup", "preset1")
    assert list(config) == [("PyDev", "propA", "valueA"), ("PyDev", "propB", "42.0")]

    # Set up event listener
    config_deleted_mock = MagicMock()
    core.events.configDeleted.connect(config_deleted_mock)

    # Delete one Python device property
    core.deleteConfig("testGroup", "preset1", "PyDev", "propA")

    # Verify event was emitted
    config_deleted_mock.assert_called_once_with("testGroup", "preset1")

    # Verify property was removed but other property remains
    config = core.getConfigData("testGroup", "preset1")
    assert list(config) == [("PyDev", "propB", "42.0")]

    # Try to delete non-existent Python property - should raise error
    with pytest.raises(RuntimeError, match="not found"):
        core.deleteConfig("testGroup", "preset1", "PyDev", "nonExistentProp")

    # Try to delete already-deleted property - should raise error
    with pytest.raises(RuntimeError, match="not found"):
        core.deleteConfig("testGroup", "preset1", "PyDev", "propA")


def test_config_with_only_python_devices():
    """Test getCurrentConfig works when config only has Python device settings."""
    core = UniMMCore()

    # Load only Python device (no C++ devices in config)
    core.loadPyDevice("PyDev", MyDevice())
    core.initializeAllDevices()

    # Create config with only Python device
    # Note: propB has limits (0.0, 100.0)
    core.defineConfigGroup("pyOnlyGroup")
    core.defineConfig("pyOnlyGroup", "preset1", "PyDev", "propB", 25.0)
    core.defineConfig("pyOnlyGroup", "preset2", "PyDev", "propB", 75.0)

    # Initially no preset matches (propB default is 10.0)
    assert core.getCurrentConfig("pyOnlyGroup") == ""

    # Set property to match preset1
    core.setProperty("PyDev", "propB", 25.0)
    assert core.getCurrentConfig("pyOnlyGroup") == "preset1"
    assert core.getCurrentConfigFromCache("pyOnlyGroup") == "preset1"

    # Change to match preset2
    core.setProperty("PyDev", "propB", 75.0)
    assert core.getCurrentConfig("pyOnlyGroup") == "preset2"

    # Set to non-matching value
    core.setProperty("PyDev", "propB", 50.0)
    assert core.getCurrentConfig("pyOnlyGroup") == ""


# =============================================================================
# Config file loading/saving tests
# =============================================================================


def test_load_system_configuration_basic(tmp_path):
    """Test loading a basic config file with C++ devices."""
    core = UniMMCore()

    # Create a minimal config file
    config_file = tmp_path / "test_config.cfg"
    config_file.write_text("""
# Test config
Device,Camera,DemoCamera,DCam
Property,Core,Initialize,1
Property,Camera,Exposure,50.0
""")

    core.loadSystemConfiguration(str(config_file))

    assert "Camera" in core.getLoadedDevices()
    assert core.getExposure() == 50.0


def test_load_system_configuration_with_python_devices(tmp_path):
    """Test loading a config file with #py prefixed Python device lines."""
    core = UniMMCore()

    # Create a config with both C++ and Python devices
    config_file = tmp_path / "test_mixed_config.cfg"
    config_file.write_text(f"""
# Test config with mixed devices
Device,Camera,DemoCamera,DCam
#py pyDevice,{PYDEV},{__name__},{MyDevice.__name__}
Property,Core,Initialize,1
Property,Camera,Exposure,100.0
#py Property,{PYDEV},{PROP_B},42.0
""")

    core.loadSystemConfiguration(str(config_file))

    # Both devices should be loaded
    assert "Camera" in core.getLoadedDevices()
    assert PYDEV in core.getLoadedDevices()

    # Properties should be set
    assert core.getExposure() == 100.0
    assert core.getProperty(PYDEV, PROP_B) == 42.0


def test_load_system_configuration_python_device_as_camera(tmp_path):
    """Test setting a Python device as the core camera via config."""
    from pymmcore_plus.experimental.unicore import CameraDevice

    # Create a simple Python camera class
    class SimplePyCamera(CameraDevice):
        def __init__(self):
            super().__init__()
            self._exp = 10.0

        def get_exposure(self):
            return self._exp

        def set_exposure(self, ms):
            self._exp = ms

        def shape(self):
            return (512, 512)

        def dtype(self):
            return "uint16"

        def start_sequence(self, n_images=None, get_buffer=None):
            # Minimal implementation for testing
            return iter([])

    # Register it in this module's namespace for import
    import sys

    this_module = sys.modules[__name__]
    this_module.SimplePyCamera = SimplePyCamera

    try:
        core = UniMMCore()

        config_file = tmp_path / "test_pycam_config.cfg"
        config_file.write_text(f"""
#py pyDevice,PyCam,{__name__},SimplePyCamera
Property,Core,Initialize,1
#py Property,Core,Camera,PyCam
""")

        core.loadSystemConfiguration(str(config_file))

        assert "PyCam" in core.getLoadedDevices()
        assert core.getCameraDevice() == "PyCam"
    finally:
        # Clean up the registered class
        delattr(this_module, "SimplePyCamera")


def test_load_system_configuration_with_config_groups(tmp_path):
    """Test loading config groups with both C++ and Python devices."""
    core = UniMMCore()

    config_file = tmp_path / "test_config_groups.cfg"
    config_file.write_text(f"""
Device,Camera,DemoCamera,DCam
#py pyDevice,{PYDEV},{__name__},{MyDevice.__name__}
Property,Core,Initialize,1
ConfigGroup,TestGroup,Preset1,Camera,Exposure,25.0
#py ConfigGroup,TestGroup,Preset1,{PYDEV},{PROP_B},10.0
ConfigGroup,TestGroup,Preset2,Camera,Exposure,100.0
#py ConfigGroup,TestGroup,Preset2,{PYDEV},{PROP_B},50.0
""")

    core.loadSystemConfiguration(str(config_file))

    # Config groups should be defined
    assert core.isGroupDefined("TestGroup")
    assert "Preset1" in core.getAvailableConfigs("TestGroup")
    assert "Preset2" in core.getAvailableConfigs("TestGroup")

    # Apply preset and verify
    core.setConfig("TestGroup", "Preset1")
    assert core.getExposure() == 25.0
    assert core.getProperty(PYDEV, PROP_B) == 10.0


def test_load_system_configuration_error_handling(tmp_path):
    """Test error handling during config loading."""
    core = UniMMCore()

    # Test file not found
    with pytest.raises(FileNotFoundError):
        core.loadSystemConfiguration("/nonexistent/path/config.cfg")

    # Test invalid command (should fail strict)
    config_file = tmp_path / "bad_config.cfg"
    config_file.write_text("""
Device,Camera,DemoCamera,DCam
Property,Core,Initialize,1
InvalidCommand,foo,bar
""")

    with pytest.raises(RuntimeError, match="Unknown configuration command"):
        core.loadSystemConfiguration(str(config_file))


def test_save_system_configuration(tmp_path):
    """Test saving a system configuration."""
    core = UniMMCore()

    # Set up a configuration
    core.loadDevice("Camera", "DemoCamera", "DCam")
    core.initializeAllDevices()
    core.setExposure(75.0)

    # Save the config
    config_file = tmp_path / "saved_config.cfg"
    core.saveSystemConfiguration(str(config_file))

    # Verify the file was created and contains expected content
    content = config_file.read_text()
    assert "Device,Camera,DemoCamera,DCam" in content
    assert "Property,Core,Initialize,1" in content


def test_save_system_configuration_with_python_devices(tmp_path):
    """Test saving config with Python devices uses #py prefix."""
    core = UniMMCore()

    # Load both C++ and Python devices
    core.loadDevice("Camera", "DemoCamera", "DCam")
    core.loadPyDevice(PYDEV, MyDevice())
    core.initializeAllDevices()
    core.setProperty(PYDEV, PROP_B, 50.0)

    # Save the config
    config_file = tmp_path / "saved_mixed_config.cfg"
    core.saveSystemConfiguration(str(config_file))

    # Check the content
    content = config_file.read_text()

    # C++ device should NOT have #py prefix
    assert "Device,Camera,DemoCamera,DCam" in content

    # Python device SHOULD have #py pyDevice prefix
    assert f"#py pyDevice,{PYDEV}," in content


def test_config_roundtrip(tmp_path):
    """Test that save then load produces the same configuration."""
    core = UniMMCore()

    # Set up initial configuration
    core.loadDevice("Camera", "DemoCamera", "DCam")
    core.loadPyDevice(PYDEV, MyDevice())
    core.initializeAllDevices()
    core.setCameraDevice("Camera")
    core.setExposure(42.0)
    core.setProperty(PYDEV, PROP_B, 25.0)

    # Define a config group with both device types
    core.defineConfigGroup("TestGroup")
    core.defineConfig("TestGroup", "Preset1", "Camera", "Exposure", 100.0)
    core.defineConfig("TestGroup", "Preset1", PYDEV, PROP_B, 75.0)

    # Save the configuration
    config_file = tmp_path / "roundtrip_config.cfg"
    core.saveSystemConfiguration(str(config_file))

    # Create a new core and load the saved config
    core2 = UniMMCore()
    core2.loadSystemConfiguration(str(config_file))

    # Verify devices are loaded
    assert "Camera" in core2.getLoadedDevices()
    assert PYDEV in core2.getLoadedDevices()

    # Verify config group exists and has correct settings
    assert core2.isGroupDefined("TestGroup")
    assert "Preset1" in core2.getAvailableConfigs("TestGroup")

    # Apply the preset and verify values
    core2.setConfig("TestGroup", "Preset1")
    assert core2.getExposure() == 100.0
    assert core2.getProperty(PYDEV, PROP_B) == 75.0


def test_config_backward_compatibility():
    """Test that regular pymmcore can load configs saved with Python devices.

    The #py prefixed lines should be treated as comments.
    """
    import os
    import tempfile

    from pymmcore_plus import CMMCorePlus

    core = UniMMCore()

    # Set up with Python device
    core.loadDevice("Camera", "DemoCamera", "DCam")
    core.loadPyDevice(PYDEV, MyDevice())
    core.initializeAllDevices()

    # Define config with Python device
    core.defineConfigGroup("Channel")
    core.defineConfig("Channel", "DAPI", "Camera", "Exposure", 50.0)
    core.defineConfig("Channel", "DAPI", PYDEV, PROP_B, 25.0)

    # Save config
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as f:
        config_path = f.name

    try:
        core.saveSystemConfiguration(config_path)

        # Load with regular CMMCorePlus (not UniMMCore)
        # The #py lines should be ignored as comments
        regular_core = CMMCorePlus()
        regular_core.loadSystemConfiguration(config_path)

        # C++ device should be loaded
        assert "Camera" in regular_core.getLoadedDevices()

        # Python device should NOT be loaded (line was treated as comment)
        assert PYDEV not in regular_core.getLoadedDevices()

        # Config group should exist but only have C++ device settings
        assert regular_core.isGroupDefined("Channel")
        config = regular_core.getConfigData("Channel", "DAPI")
        settings = list(config)
        # Should only have Camera settings, not Python device settings
        assert all(d != PYDEV for d, p, v in settings)
    finally:
        os.unlink(config_path)


def test_load_config_with_labels_and_state_devices(tmp_path):
    """Test loading state device labels from config."""
    core = UniMMCore()

    config_file = tmp_path / "test_labels.cfg"
    config_file.write_text("""
Device,Filter,DemoCamera,DWheel
Property,Core,Initialize,1
Label,Filter,0,DAPI
Label,Filter,1,FITC
Label,Filter,2,Cy5
""")

    core.loadSystemConfiguration(str(config_file))

    assert "Filter" in core.getLoadedDevices()
    labels = core.getStateLabels("Filter")
    assert labels[0] == "DAPI"
    assert labels[1] == "FITC"
    assert labels[2] == "Cy5"
