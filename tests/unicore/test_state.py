from typing import Any

import pytest

from pymmcore_plus.experimental.unicore import StateDevice
from pymmcore_plus.experimental.unicore.core._unicore import UniMMCore

DEV = "StateDevice"


class MyStateDevice(StateDevice):
    """Example State device (e.g., filter wheel, objective turret)."""

    def __init__(self, num_positions: int = 4) -> None:
        """Initialize state device with default labels."""
        state_labels = {i: f"Position-{i}" for i in range(num_positions)}
        super().__init__(state_labels)
        self._current_position = 0

    def set_position(self, pos: int | str) -> None:
        """Set the position of the device."""
        if isinstance(pos, str):
            pos = self.get_position_for_label(pos)
        if pos not in self._states:
            raise ValueError(f"Position {pos} is not a valid state.")
        self._current_position = pos
        self.set_property_value("State", pos)

    def get_current_position(self) -> int:
        """Return the current position of the device."""
        return self._current_position


class MyFilterWheel(StateDevice):
    """Example Filter Wheel state device."""

    def __init__(self) -> None:
        """Initialize filter wheel with filter names."""
        filter_labels = {0: "Empty", 1: "DAPI", 2: "FITC", 3: "Texas Red", 4: "Cy5"}
        super().__init__(filter_labels)
        self._current_position = 0


class MyObjectiveTurret(StateDevice):
    """Example Objective Turret state device."""

    def __init__(self) -> None:
        """Initialize objective turret with objective names."""
        objective_labels = {0: "10X", 1: "20X", 2: "40X", 3: "100X"}
        super().__init__(objective_labels)
        self._current_position = 0


def _load_state_device(
    core: UniMMCore, device: str, cls: type = MyStateDevice, **kwargs: Any
) -> None:
    """Load either a Python or C++ State device."""
    if DEV in core.getLoadedDevices():
        core.unloadDevice(DEV)

    if device == "python":
        state_dev = cls(**kwargs)
        core.loadPyDevice(DEV, state_dev)
    elif device == "cpp":
        # Load a C++ state device (like Demo's Objective)
        core.loadDevice(DEV, "DemoCamera", "DObjective")
        core.initializeDevice(DEV)
    else:
        raise ValueError(f"Unknown device type: {device}")


@pytest.fixture(params=["python", "cpp"])
def loaded_state_core(request: pytest.FixtureRequest) -> UniMMCore:
    """Fixture providing a core with a loaded state device."""
    core = UniMMCore()
    _load_state_device(core, request.param)
    return core


def test_python_state_device_creation() -> None:
    """Test creating Python state devices with different configurations."""
    # Test with number of positions
    device1 = MyStateDevice(3)
    assert device1.get_number_of_positions() == 3

    # Test with state labels mapping
    state_labels = {0: "Red", 1: "Green", 2: "Blue"}
    device2 = StateDevice(state_labels)
    assert device2.get_number_of_positions() == 3
    assert device2.get_label_for_position(0) == "Red"
    assert device2.get_label_for_position(1) == "Green"
    assert device2.get_label_for_position(2) == "Blue"


def test_state_device_basic_functionality(loaded_state_core: UniMMCore) -> None:
    """Test basic state device operations."""
    core = loaded_state_core

    # Test getting current state
    initial_state = core.getState(DEV)
    assert isinstance(initial_state, int)
    assert initial_state >= 0

    # Test getting number of states
    num_states = core.getNumberOfStates(DEV)
    assert isinstance(num_states, int)
    assert num_states > 0

    # Test getting current state label
    initial_label = core.getStateLabel(DEV)
    assert isinstance(initial_label, str)
    assert len(initial_label) > 0


def test_set_state_by_position(loaded_state_core: UniMMCore) -> None:
    """Test setting state by position number."""
    core = loaded_state_core

    core.getState(DEV)
    num_states = core.getNumberOfStates(DEV)

    # Test setting different states
    for new_state in range(min(3, num_states)):
        core.setState(DEV, new_state)
        assert core.getState(DEV) == new_state

        # Verify label is updated too
        label = core.getStateLabel(DEV)
        assert isinstance(label, str)
        assert len(label) > 0


def test_set_state_by_label(loaded_state_core: UniMMCore) -> None:
    """Test setting state by label string."""
    core = loaded_state_core

    # Get all available labels
    labels = core.getStateLabels(DEV)

    assert len(labels) > 0

    # Test setting state by each available label
    for label in labels[:3]:  # Test first 3 labels
        core.setStateLabel(DEV, label)
        assert core.getStateLabel(DEV) == label

        # Verify position is updated correctly
        expected_position = core.getStateFromLabel(DEV, label)
        assert core.getState(DEV) == expected_position


def test_define_state_label(loaded_state_core: UniMMCore) -> None:
    """Test defining custom labels for states."""
    core = loaded_state_core

    num_states = core.getNumberOfStates(DEV)
    if num_states == 0:
        pytest.skip("Device has no states")

    # Define a new label for the first state
    custom_label = "CustomLabel"
    core.defineStateLabel(DEV, 0, custom_label)

    # Verify the label was set
    labels = core.getStateLabels(DEV)
    assert custom_label in labels

    # Verify we can set state using the custom label
    core.setStateLabel(DEV, custom_label)
    assert core.getState(DEV) == 0
    assert core.getStateLabel(DEV) == custom_label


def test_get_state_labels(loaded_state_core: UniMMCore) -> None:
    """Test getting all state labels."""
    core = loaded_state_core

    labels = core.getStateLabels(DEV)

    num_states = core.getNumberOfStates(DEV)
    assert len(labels) == num_states

    # All labels should be strings
    for label in labels:
        assert isinstance(label, str)
        assert len(label) > 0


def test_get_state_from_label(loaded_state_core: UniMMCore) -> None:
    """Test getting state position from label."""
    core = loaded_state_core

    labels = core.getStateLabels(DEV)

    for i, label in enumerate(labels):
        position = core.getStateFromLabel(DEV, label)
        assert position == i


def test_state_consistency(loaded_state_core: UniMMCore) -> None:
    """Test consistency between different state methods."""
    core = loaded_state_core

    num_states = core.getNumberOfStates(DEV)
    labels = core.getStateLabels(DEV)

    # Number of labels should match number of states
    assert len(labels) == num_states

    # Test each state position
    for i in range(num_states):
        # Set state by position
        core.setState(DEV, i)

        # Verify consistency
        assert core.getState(DEV) == i

        current_label = core.getStateLabel(DEV)
        assert current_label == labels[i]

        position_from_label = core.getStateFromLabel(DEV, current_label)
        assert position_from_label == i


def test_python_filter_wheel() -> None:
    """Test specific filter wheel functionality."""
    core = UniMMCore()
    _load_state_device(core, "python", MyFilterWheel)

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
    _load_state_device(core, "python", MyObjectiveTurret)

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


def test_error_handling(loaded_state_core: UniMMCore) -> None:
    """Test error handling for invalid operations."""
    core = loaded_state_core

    num_states = core.getNumberOfStates(DEV)

    # Test setting invalid state position (only for Python devices)
    if DEV in core._pydevices._devices:
        with pytest.raises(ValueError):
            core.setState(DEV, num_states + 10)  # Way out of range

    # Test setting invalid state label
    with pytest.raises(RuntimeError, match="Label not defined"):
        core.setStateLabel(DEV, "Undefined")

    # Test getting state from invalid label
    with pytest.raises(RuntimeError, match="Label not defined"):
        core.getStateFromLabel(DEV, "Undefined")


def test_state_device_registration() -> None:
    """Test registering and unregistering state devices."""
    core = UniMMCore()
    # Create a custom state device
    custom_device = MyStateDevice(3)

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
    filter_wheel = MyFilterWheel()
    objective_turret = MyObjectiveTurret()

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
    _load_state_device(core, "cpp")

    # Verify it works through UniMMCore
    initial_state = core.getState(DEV)
    assert isinstance(initial_state, int)

    labels = core.getStateLabels(DEV)

    assert len(labels) > 0

    # Test setting state
    if len(labels) > 1:
        core.setStateLabel(DEV, labels[1])
        assert core.getStateLabel(DEV) == labels[1]


def test_concurrent_state_operations(loaded_state_core: UniMMCore) -> None:
    """Test concurrent state operations don't interfere."""
    core = loaded_state_core

    num_states = core.getNumberOfStates(DEV)
    if num_states < 2:
        pytest.skip("Need at least 2 states for this test")

    # Rapidly switch between states
    for _ in range(10):
        core.setState(DEV, 0)
        assert core.getState(DEV) == 0

        core.setState(DEV, 1)
        assert core.getState(DEV) == 1
