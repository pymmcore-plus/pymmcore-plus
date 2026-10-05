from __future__ import annotations

import threading
from typing import Any
from unittest.mock import Mock, call

import pytest

from pymmcore_plus.core._constants import Keyword
from pymmcore_plus.experimental.unicore import StateDevice
from pymmcore_plus.experimental.unicore.core._unicore import UniMMCore

DEV = "StateDevice"


class MyStateDevice(StateDevice):
    """Example State device (e.g., filter wheel, objective turret)."""

    _current_position: int = 0

    def set_state(self, pos: int) -> None:
        """Set the position of the device."""
        self._current_position = pos

    def get_state(self) -> int:
        """Return the current position of the device."""
        return self._current_position


def _load_state_device(core: UniMMCore, adapter: MyStateDevice | None = None) -> None:
    """Load either a Python or C++ State device."""
    if DEV in core.getLoadedDevices():
        core.unloadDevice(DEV)

    if adapter is not None:
        core.loadPyDevice(DEV, adapter)
    else:
        # Load a C++ state device (like Demo's Objective)
        core.loadDevice(DEV, "DemoCamera", "DWheel")
    core.initializeDevice(DEV)


@pytest.fixture(params=["python", "cpp"])
def unicore(request: pytest.FixtureRequest) -> UniMMCore:
    """Fixture providing a core with a loaded state device."""
    core = UniMMCore()
    dev = MyStateDevice.from_count(10) if request.param == "python" else None
    _load_state_device(core, dev)
    # Store the parameter type for easy access in tests
    core._test_device_type = request.param  # type: ignore[assignment]
    return core


def test_python_state_device_creation() -> None:
    """Test creating Python state devices with different configurations."""
    # Test with number of positions
    core = UniMMCore()
    device1 = MyStateDevice({0: "Red", 1: "Green", 2: "Blue"})
    core.loadPyDevice(DEV, device1)

    assert core.getNumberOfStates(DEV) == 3
    assert core.getStateLabels(DEV) == ("Red", "Green", "Blue")


def test_state_device_basic_functionality(unicore: UniMMCore) -> None:
    """Test basic state device operations."""

    # Test getting current state
    initial_state = unicore.getState(DEV)
    assert isinstance(initial_state, int)
    assert initial_state == 0

    # Test getting number of states
    num_states = unicore.getNumberOfStates(DEV)
    assert isinstance(num_states, int)
    assert num_states == 10  # both c++ and the default fixture python dev

    # Test getting current state label
    initial_label = unicore.getStateLabel(DEV)
    assert isinstance(initial_label, str)
    assert initial_label == "State-0"


def test_set_state_by_position(unicore: UniMMCore) -> None:
    """Test setting state by position number."""
    unicore.getState(DEV)
    num_states = unicore.getNumberOfStates(DEV)

    # Test setting different states
    for new_state in range(min(3, num_states)):
        unicore.setState(DEV, new_state)
        assert unicore.getState(DEV) == new_state
        assert str(unicore.getProperty(DEV, Keyword.State)) == str(new_state)

        # Verify label is updated too
        label = unicore.getStateLabel(DEV)
        assert isinstance(label, str)
        assert len(label) > 0


def test_set_state_by_state_property(unicore: UniMMCore) -> None:
    """Test setting state by position number."""
    unicore.getState(DEV)
    # Test setting by property rather than direct method
    for new_state in range(3):
        unicore.setProperty(DEV, Keyword.State, new_state)
        assert unicore.getState(DEV) == new_state
        assert unicore.getStateLabel(DEV) == f"State-{new_state}"


def test_set_state_by_label_property(unicore: UniMMCore) -> None:
    """Test setting state by label property."""
    unicore.getState(DEV)
    labels = unicore.getStateLabels(DEV)

    # Test setting state by label
    for label in labels[:3]:
        unicore.setProperty(DEV, Keyword.Label.value, label)
        assert unicore.getStateLabel(DEV) == label

        # Verify position is updated correctly
        expected_position = unicore.getStateFromLabel(DEV, label)
        assert unicore.getState(DEV) == expected_position


def test_set_state_by_label(unicore: UniMMCore) -> None:
    """Test setting state by label string."""
    # Get all available labels
    labels = unicore.getStateLabels(DEV)
    assert len(labels) > 0

    # Test setting state by each available label
    for label in labels:
        unicore.setStateLabel(DEV, label)
        assert unicore.getStateLabel(DEV) == label

        # Verify position is updated correctly
        expected_position = unicore.getStateFromLabel(DEV, label)
        assert unicore.getState(DEV) == expected_position


def test_define_state_label(unicore: UniMMCore) -> None:
    """Test defining custom labels for states."""
    num_states = unicore.getNumberOfStates(DEV)
    if num_states == 0:
        pytest.skip("Device has no states")

    if unicore._test_device_type == "python":  # type: ignore
        allowed_states = unicore.getAllowedPropertyValues(DEV, Keyword.State)
        assert allowed_states == tuple(
            str(i) for i in range(unicore.getNumberOfStates(DEV))
        )

        allowed_labels = unicore.getAllowedPropertyValues(DEV, Keyword.Label.value)
        assert allowed_labels == tuple(unicore.getStateLabels(DEV))

    # Define a new label for the first state
    custom_label = "CustomLabel"
    unicore.defineStateLabel(DEV, 7, custom_label)

    # Verify the label was set
    labels = unicore.getStateLabels(DEV)
    assert custom_label in labels

    if unicore._test_device_type == "python":  # type: ignore
        assert "CustomLabel" in unicore.getAllowedPropertyValues(
            DEV, Keyword.Label.value
        )

    # Verify we can set state using the custom label
    unicore.setStateLabel(DEV, custom_label)
    assert unicore.getState(DEV) == 7
    assert unicore.getStateLabel(DEV) == custom_label


def test_get_state_labels(unicore: UniMMCore) -> None:
    """Test getting all state labels."""
    labels = unicore.getStateLabels(DEV)

    num_states = unicore.getNumberOfStates(DEV)
    assert len(labels) == num_states

    # All labels should be strings
    for label in labels:
        assert isinstance(label, str)
        assert len(label) > 0


def test_get_state_from_label(unicore: UniMMCore) -> None:
    """Test getting state position from label."""

    labels = unicore.getStateLabels(DEV)

    for i, label in enumerate(labels):
        position = unicore.getStateFromLabel(DEV, label)
        assert position == i


def test_state_consistency(unicore: UniMMCore) -> None:
    """Test consistency between different state methods."""
    num_states = unicore.getNumberOfStates(DEV)
    labels = unicore.getStateLabels(DEV)

    # Number of labels should match number of states
    assert len(labels) == num_states

    # Test each state position
    for i in range(num_states):
        # Set state by position
        unicore.setState(DEV, i)

        # Verify consistency
        assert unicore.getState(DEV) == i

        current_label = unicore.getStateLabel(DEV)
        assert current_label == labels[i]

        position_from_label = unicore.getStateFromLabel(DEV, current_label)
        assert position_from_label == i


def test_python_filter_wheel() -> None:
    """Test specific filter wheel functionality."""
    core = UniMMCore()
    _load_state_device(
        core,
        MyStateDevice({0: "Empty", 1: "DAPI", 2: "FITC", 3: "Texas Red", 4: "Cy5"}),
    )

    # Test filter-specific functionality
    assert core.getNumberOfStates(DEV) == 5

    labels = core.getStateLabels(DEV)
    expected_filters = ("Empty", "DAPI", "FITC", "Texas Red", "Cy5")
    assert labels == expected_filters

    # Test setting filter by name
    core.setStateLabel(DEV, "DAPI")
    assert core.getState(DEV) == 1
    assert core.getStateLabel(DEV) == "DAPI"

    core.setStateLabel(DEV, "Texas Red")
    assert core.getState(DEV) == 3
    assert core.getStateLabel(DEV) == "Texas Red"


def test_python_objective_turret() -> None:
    """Test specific objective turret functionality."""
    core = UniMMCore()
    _load_state_device(core, MyStateDevice({0: "10X", 1: "20X", 2: "40X", 3: "100X"}))

    # Test objective-specific functionality
    assert core.getNumberOfStates(DEV) == 4

    labels = core.getStateLabels(DEV)
    expected_objectives = ("10X", "20X", "40X", "100X")
    assert labels == expected_objectives

    # Test setting objective by name
    core.setStateLabel(DEV, "40X")
    assert core.getState(DEV) == 2
    assert core.getStateLabel(DEV) == "40X"

    core.setStateLabel(DEV, "100X")
    assert core.getState(DEV) == 3
    assert core.getStateLabel(DEV) == "100X"


def test_error_handling(unicore: UniMMCore) -> None:
    """Test error handling for invalid operations."""
    num_states = unicore.getNumberOfStates(DEV)

    # Test setting invalid state position (only for Python devices)
    if DEV in unicore._pydevices._devices:
        with pytest.raises(ValueError):
            unicore.setState(DEV, num_states + 10)  # Way out of range

    # Test setting invalid state label
    with pytest.raises(RuntimeError, match="Label not defined"):
        unicore.setStateLabel(DEV, "Undefined")

    # Test getting state from invalid label
    with pytest.raises(RuntimeError, match="Label not defined"):
        unicore.getStateFromLabel(DEV, "Undefined")


def test_state_device_registration() -> None:
    """Test registering and unregistering state devices."""
    core = UniMMCore()
    # Create a custom state device
    custom_device = MyStateDevice.from_count(3)

    # Register the device
    core.loadPyDevice(DEV, custom_device)
    assert DEV in core.getLoadedDevices()

    # Test device functionality
    assert core.getNumberOfStates(DEV) == 3
    core.setState(DEV, 1)
    assert core.getState(DEV) == 1

    # Unregister the device
    core.unloadDevice(DEV)
    assert DEV not in core.getLoadedDevices()


def test_multiple_state_devices() -> None:
    """Test working with multiple state devices simultaneously."""
    core = UniMMCore()

    # Register multiple state devices
    filter_wheel = MyStateDevice(
        {0: "Empty", 1: "DAPI", 2: "FITC", 3: "Texas Red", 4: "Cy5"}
    )
    objective_turret = MyStateDevice({0: "10X", 1: "20X", 2: "40X", 3: "100X"})

    core.loadPyDevice("FilterWheel", filter_wheel)
    core.loadPyDevice("Objective", objective_turret)

    # Test both devices work independently
    core.setState("FilterWheel", 2)  # FITC
    core.setState("Objective", 1)  # 20X

    assert core.getState("FilterWheel") == 2
    assert core.getStateLabel("FilterWheel") == "FITC"

    assert core.getState("Objective") == 1
    assert core.getStateLabel("Objective") == "20X"

    # Clean up
    core.unloadDevice("FilterWheel")
    core.unloadDevice("Objective")


def test_state_device_with_cpp_fallback() -> None:
    """Test that C++ devices work when Python device is not available."""
    core = UniMMCore()

    # Load a C++ state device
    _load_state_device(core, None)

    # Verify it works through UniMMCore
    initial_state = core.getState(DEV)
    assert isinstance(initial_state, int)

    labels = core.getStateLabels(DEV)

    assert len(labels) > 0

    # Test setting state
    if len(labels) > 1:
        core.setStateLabel(DEV, labels[1])
        assert core.getStateLabel(DEV) == labels[1]


def test_concurrent_state_operations(unicore: UniMMCore) -> None:
    """Test concurrent state operations don't interfere."""
    num_states = unicore.getNumberOfStates(DEV)
    if num_states < 2:
        pytest.skip("Need at least 2 states for this test")

    # Rapidly switch between states
    for _ in range(10):
        unicore.setState(DEV, 0)
        assert unicore.getState(DEV) == 0

        unicore.setState(DEV, 1)
        assert unicore.getState(DEV) == 1


def test_emission_of_state_and_property() -> None:
    """Test the event onPropertyChange emitted by the StateDevice"""
    core = UniMMCore()
    prop_changed = Mock()
    core.events.propertyChanged.connect(prop_changed)

    my_state_device = MyStateDevice({0: "Red", 1: "Green", 2: "Blue"})
    dev = "MyStateDevice"
    core.loadPyDevice(dev, my_state_device)

    core.setProperty(dev, "State", 2)
    assert core.getState(dev) == 2
    assert prop_changed.call_count == 2
    prop_changed.assert_has_calls([call(dev, "State", 2), call(dev, "Label", "Blue")])

    prop_changed.reset_mock()
    core.setProperty(dev, "Label", "Green")
    assert prop_changed.call_count == 2
    prop_changed.assert_has_calls([call(dev, "State", 1), call(dev, "Label", "Green")])

    prop_changed.reset_mock()
    core.setState(dev, 0)
    assert core.getState(dev) == 0
    assert prop_changed.call_count == 2
    prop_changed.assert_has_calls([call(dev, "State", 0), call(dev, "Label", "Red")])

    prop_changed.reset_mock()
    core.setStateLabel(dev, "Blue")
    assert core.getState(dev) == 2
    assert prop_changed.call_count == 2
    prop_changed.assert_has_calls([call(dev, "State", 2), call(dev, "Label", "Blue")])


def test_property_changed_is_emitted_after_cache_update_and_unlock() -> None:
    """Listeners see the new cached State/Label and may call back into the device.

    e.g. a widget re-matching config presets from the cache in response to the
    signal must see the new values, and calling `setConfig` from the listener must not
    deadlock on the (non-reentrant) device lock.
    """
    core = UniMMCore()
    wheels = {
        "LED": MyStateDevice({0: "CYAN", 1: "UV"}),
        "Filter": MyStateDevice({0: "em450", 1: "em520"}),
    }
    for name, wheel in wheels.items():
        core.loadPyDevice(name, wheel)
        core.initializeDevice(name)
    for preset, led, flt in (("brightfield", "CYAN", "em450"), ("DAPI", "UV", "em520")):
        core.defineConfig("Channel", preset, "LED", "Label", led)
        core.defineConfig("Channel", preset, "Filter", "Label", flt)
    core.setConfig("Channel", "brightfield")

    problems: list[tuple[str, str, str]] = []

    def _check(dev: str, prop: str, value: Any) -> None:
        if str(core.getPropertyFromCache(dev, prop)) != str(value):
            problems.append(("stale cache", dev, prop))
        if wheels[dev].locked():
            problems.append(("device lock held", dev, prop))

    core.events.propertyChanged.connect(_check)
    core.setConfig("Channel", "DAPI")
    assert problems == []


def test_device_initiated_state_change_emits_immediately() -> None:
    """A state device reporting a move of its own (e.g. by hand) emits right away."""
    core = UniMMCore()
    wheel = MyStateDevice({0: "Red", 1: "Green", 2: "Blue"})
    dev = "MyStateDevice"
    core.loadPyDevice(dev, wheel)
    core.initializeDevice(dev)

    prop_changed = Mock()
    core.events.propertyChanged.connect(prop_changed)

    wheel._current_position = 1  # moved by hand, not via the core
    wheel.notify_state_changed(1)
    assert prop_changed.call_args_list == [
        call(dev, "State", 1),
        call(dev, "Label", "Green"),
    ]

    # a later core call emits only its own changes, no leftovers
    prop_changed.reset_mock()
    core.setState(dev, 2)
    assert prop_changed.call_args_list == [
        call(dev, "State", 2),
        call(dev, "Label", "Blue"),
    ]


def test_device_initiated_state_change_updates_cache_first() -> None:
    """Listeners of a device-initiated move see the new value in the cache."""
    core = UniMMCore()
    wheel = MyStateDevice({0: "Red", 1: "Green", 2: "Blue"})
    dev = "MyStateDevice"
    core.loadPyDevice(dev, wheel)
    core.initializeDevice(dev)

    seen: list[tuple[str, Any, Any]] = []
    core.events.propertyChanged.connect(
        lambda d, p, v: seen.append((p, v, core.getPropertyFromCache(d, p)))
    )
    wheel._current_position = 2  # moved by hand, not via the core
    wheel.notify_state_changed(2)
    assert seen == [("State", 2, 2), ("Label", "Blue", "Blue")]


class _GatedStateDevice(MyStateDevice):
    """Blocks inside set_state(1) until `release` is set, to hold a core call open."""

    def __init__(self, labels: dict[int, str]) -> None:
        super().__init__(labels)
        self.entered = threading.Event()
        self.release = threading.Event()

    def set_state(self, pos: int) -> None:
        if pos == 1:
            self.entered.set()
            assert self.release.wait(5)
        super().set_state(pos)


def test_device_move_during_core_call_on_another_thread() -> None:
    """A device-initiated move is not folded into a core call running elsewhere."""
    core = UniMMCore()
    wheel = _GatedStateDevice({0: "Red", 1: "Green", 2: "Blue"})
    dev = "MyStateDevice"
    core.loadPyDevice(dev, wheel)
    core.initializeDevice(dev)

    seen: list[tuple[str, Any, str]] = []
    core.events.propertyChanged.connect(
        lambda d, p, v: seen.append((p, v, threading.current_thread().name))
    )

    # a core call on another thread, held open inside the device's set_state(1)
    t = threading.Thread(target=core.setState, args=(dev, 1), name="core-call")
    t.start()
    assert wheel.entered.wait(5)

    # meanwhile, the device moves on its own (this thread plays the device's thread)
    wheel._current_position = 2
    wheel.notify_state_changed(2)
    me = threading.current_thread().name
    assert seen == [("State", 2, me), ("Label", "Blue", me)]  # emitted right away

    wheel.release.set()
    t.join(5)
    assert not t.is_alive()
    # the core call emits only its own move, after it finishes, on its own thread
    assert seen[2:] == [("State", 1, "core-call"), ("Label", "Green", "core-call")]


class _CoupledStateDevice(MyStateDevice):
    """Moves another state device from its own set_state.

    Like C++ devices that drive other devices (e.g. Utilities' StateDeviceShutter).
    """

    def __init__(self, labels: dict[int, str], other: StateDevice) -> None:
        super().__init__(labels)
        self.other = other

    def set_state(self, pos: int) -> None:
        super().set_state(pos)
        self.other.set_property_value("State", pos)
        self.other.notify_state_changed(pos)


def test_core_call_that_moves_a_second_device() -> None:
    """Events of a second device moved inside a core call wait for that call."""
    core = UniMMCore()
    filt = MyStateDevice({0: "em450", 1: "em520"})
    turret = _CoupledStateDevice({0: "10x", 1: "60x"}, other=filt)
    core.loadPyDevice("Filter", filt)
    core.loadPyDevice("Turret", turret)
    core.initializeDevice("Filter")
    core.initializeDevice("Turret")
    devices = {"Filter": filt, "Turret": turret}

    seen: list[tuple[str, str, Any]] = []
    problems: list[tuple[str, str, str]] = []

    def _check(dev: str, prop: str, value: Any) -> None:
        seen.append((dev, prop, value))
        if str(core.getPropertyFromCache(dev, prop)) != str(value):
            problems.append(("stale cache", dev, prop))
        if any(d.locked() for d in devices.values()):
            problems.append(("a device lock is held", dev, prop))

    core.events.propertyChanged.connect(_check)
    core.setState("Turret", 1)
    assert problems == []
    assert seen == [
        ("Filter", "State", 1),
        ("Filter", "Label", "em520"),
        ("Turret", "State", 1),
        ("Turret", "Label", "60x"),
    ]


def test_cached_state_and_label_follow_the_device(unicore: UniMMCore) -> None:
    """getPropertyFromCache sees State/Label after every way of moving the device.

    CMMCore refreshes its state cache for both keywords on setState and
    setStateLabel. Cached config lookups (e.g. getCurrentPixelSizeConfig(True),
    which MDA summary metadata uses) read the cache, so a stale entry makes
    them resolve the previous position.
    """
    core = unicore
    core.defineStateLabel(DEV, 1, "one")
    core.defineStateLabel(DEV, 2, "two")
    core.defineStateLabel(DEV, 3, "three")
    core.setState(DEV, 0)

    core.setState(DEV, 1)
    assert str(core.getPropertyFromCache(DEV, Keyword.State)) == "1"
    assert str(core.getPropertyFromCache(DEV, Keyword.Label)) == "one"

    core.setStateLabel(DEV, "two")
    assert str(core.getPropertyFromCache(DEV, Keyword.State)) == "2"
    assert str(core.getPropertyFromCache(DEV, Keyword.Label)) == "two"

    core.setProperty(DEV, Keyword.State, 3)
    assert str(core.getPropertyFromCache(DEV, Keyword.State)) == "3"
    assert str(core.getPropertyFromCache(DEV, Keyword.Label)) == "three"

    core.setProperty(DEV, Keyword.Label, "one")
    assert str(core.getPropertyFromCache(DEV, Keyword.State)) == "1"
    assert str(core.getPropertyFromCache(DEV, Keyword.Label)) == "one"
