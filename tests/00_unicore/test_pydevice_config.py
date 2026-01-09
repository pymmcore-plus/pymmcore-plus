"""Test loading config files with Python devices replacing C++ devices."""

from __future__ import annotations

from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.experimental.unicore import StateDevice, UniMMCore

if TYPE_CHECKING:
    from pathlib import Path

# A simple Python state device that simulates a filter wheel
# This replaces the DemoCamera DWheel device


class PyFilterWheel(StateDevice):
    """A simple Python filter wheel device with 5 positions."""

    _current_state: int = 0

    def __init__(self) -> None:
        # Initialize with 5 filter positions
        super().__init__(
            {
                0: "Empty",
                1: "DAPI",
                2: "FITC",
                3: "TRITC",
                4: "Cy5",
            }
        )

    def get_state(self) -> int:
        return self._current_state

    def set_state(self, position: int) -> None:
        self._current_state = position


# Minimal config with a mix of C++ and Python devices
# The Dichroic filter wheel is replaced by our PyFilterWheel
MIXED_CONFIG = dedent("""
# Minimal config with Python device replacing C++ DWheel

# Reset
Property,Core,Initialize,0

# C++ Devices from DemoCamera
Device,DHub,DemoCamera,DHub
Device,Camera,DemoCamera,DCam
Device,Z,DemoCamera,DStage
Device,Emission,DemoCamera,DWheel

# Python device (ignored by regular pymmcore due to #py prefix)
#py pyDevice,Dichroic,tests.00_unicore.test_pydevice_config,PyFilterWheel

# Initialize
Property,Core,Initialize,1

# Roles
Property,Core,Camera,Camera
Property,Core,Focus,Z

# Labels for the C++ Emission filter wheel
Label,Emission,0,Chroma-HQ620
Label,Emission,1,Chroma-D460
Label,Emission,2,Chroma-HQ535
Label,Emission,3,Chroma-HQ700

# Labels for the Python filter wheel (prefixed with #py for backward compatibility)
#py Label,Dichroic,0,Empty
#py Label,Dichroic,1,DAPI
#py Label,Dichroic,2,FITC
#py Label,Dichroic,3,TRITC
#py Label,Dichroic,4,Cy5

# Config groups using BOTH C++ (Emission) and Python (Dichroic) devices
ConfigGroup,Channel,DAPI,Emission,Label,Chroma-D460
#py ConfigGroup,Channel,DAPI,Dichroic,Label,DAPI
ConfigGroup,Channel,FITC,Emission,Label,Chroma-HQ535
#py ConfigGroup,Channel,FITC,Dichroic,Label,FITC
ConfigGroup,Channel,TRITC,Emission,Label,Chroma-HQ700
#py ConfigGroup,Channel,TRITC,Dichroic,Label,TRITC
""").strip()


@pytest.fixture
def mixed_cfg_path(tmp_path: Path) -> Path:
    """Create a temporary config file."""
    path = tmp_path / "config.cfg"
    path.write_text(MIXED_CONFIG)
    return path


def test_load_mixed_config(mixed_cfg_path: Path) -> None:
    """Test that UniMMCore can load a config with both device types."""
    core = UniMMCore()
    core.loadSystemConfiguration(str(mixed_cfg_path))

    # Check C++ devices are loaded
    assert "Camera" in core.getLoadedDevices()
    assert "Z" in core.getLoadedDevices()
    assert "Emission" in core.getLoadedDevices()

    # Check Python device is loaded
    assert "Dichroic" in core.getLoadedDevices()

    assert core.isPyDevice("Dichroic")
    assert core.getDeviceLibrary("Dichroic") == "tests.00_unicore.test_pydevice_config"
    assert core.getDeviceName("Dichroic") == "PyFilterWheel"
    assert not core.isPyDevice("Emission")


def test_python_device_labels(mixed_cfg_path: Path) -> None:
    """Test that labels are correctly applied to Python devices."""
    core = UniMMCore()
    core.loadSystemConfiguration(str(mixed_cfg_path))

    # Check state labels were applied
    labels = core.getStateLabels("Dichroic")
    assert "Empty" in labels
    assert "DAPI" in labels
    assert "FITC" in labels
    assert "TRITC" in labels
    assert "Cy5" in labels


def test_python_device_state_operations(mixed_cfg_path: Path) -> None:
    """Test that Python device state can be read and set."""
    core = UniMMCore()
    core.loadSystemConfiguration(str(mixed_cfg_path))

    # Set state by position
    core.setState("Dichroic", 2)
    assert core.getState("Dichroic") == 2
    assert core.getStateLabel("Dichroic") == "FITC"

    # Set state by label
    core.setStateLabel("Dichroic", "DAPI")
    assert core.getState("Dichroic") == 1


def test_config_groups_with_mixed_devices(mixed_cfg_path: Path) -> None:
    """Test that config groups with both C++ and Python devices work correctly."""
    core = UniMMCore()
    core.loadSystemConfiguration(str(mixed_cfg_path))

    # Apply the FITC channel config - should set BOTH devices
    core.setConfig("Channel", "FITC")
    assert core.getStateLabel("Dichroic") == "FITC"
    assert core.getStateLabel("Emission") == "Chroma-HQ535"

    core.setConfig("Channel", "DAPI")
    assert core.getStateLabel("Dichroic") == "DAPI"
    assert core.getStateLabel("Emission") == "Chroma-D460"

    core.setConfig("Channel", "TRITC")
    assert core.getStateLabel("Dichroic") == "TRITC"
    assert core.getStateLabel("Emission") == "Chroma-HQ700"


def test_backward_compatibility_with_regular_core(mixed_cfg_path: Path) -> None:
    """Test that the config file gracefully degrades with regular CMMCorePlus.

    The Python device lines are commented out with #py, so regular CMMCorePlus
    should be able to load the file (though it will skip those devices).
    """
    core = CMMCorePlus()
    # Should not raise - the #py lines are treated as comments
    core.loadSystemConfiguration(str(mixed_cfg_path))

    # C++ devices should be loaded
    assert "Camera" in core.getLoadedDevices()
    assert "Z" in core.getLoadedDevices()
    assert "Emission" in core.getLoadedDevices()

    # Python device is NOT loaded (it's a comment in regular pymmcore)
    assert "Dichroic" not in core.getLoadedDevices()

    # Config groups should still work for C++ devices
    core.setConfig("Channel", "FITC")
    assert core.getStateLabel("Emission") == "Chroma-HQ535"

    core.setConfig("Channel", "DAPI")
    assert core.getStateLabel("Emission") == "Chroma-D460"


def test_save_and_reload_mixed_config(mixed_cfg_path: Path, tmp_path: Path) -> None:
    """Test that a mixed config can be saved and reloaded."""
    core = UniMMCore()
    core.loadSystemConfiguration(str(mixed_cfg_path))

    # Modify the Python device state
    core.setState("Dichroic", 3)

    # Save the configuration
    save_path = tmp_path / "saved_config.cfg"
    core.saveSystemConfiguration(str(save_path))

    # Load the saved config into a new core
    core2 = UniMMCore()
    core2.loadSystemConfiguration(str(save_path))

    # Verify Python device is still present and functional
    assert "Dichroic" in core2.getLoadedDevices()
    assert core2.isPyDevice("Dichroic")
    # Class is dynamically loaded, so check name instead of isinstance
    assert core2.getDeviceLibrary("Dichroic") == "tests.00_unicore.test_pydevice_config"
    assert core2.getDeviceName("Dichroic") == "PyFilterWheel"

    # Verify labels are preserved
    labels = core2.getStateLabels("Dichroic")
    assert "TRITC" in labels


def test_save_without_py_prefix(mixed_cfg_path: Path, tmp_path: Path) -> None:
    """Test saving config with prefix_py_devices=False."""
    core = UniMMCore()
    core.loadSystemConfiguration(str(mixed_cfg_path))

    # Save the configuration WITHOUT #py prefix
    save_path = tmp_path / "saved_no_prefix.cfg"
    core.saveSystemConfiguration(str(save_path), prefix_py_devices=False)

    # Read the saved content
    content = save_path.read_text()

    # Python device lines should NOT have #py prefix
    assert "pyDevice,Dichroic," in content
    assert "#py pyDevice,Dichroic," not in content

    # C++ device lines should still be normal
    assert "Device,Camera,DemoCamera,DCam" in content

    # UniMMCore should still be able to load it
    core2 = UniMMCore()
    core2.loadSystemConfiguration(str(save_path))
    assert "Dichroic" in core2.getLoadedDevices()
    assert "Camera" in core2.getLoadedDevices()

    # Regular CMMCorePlus should fail (pyDevice is unknown, and subsequent
    # commands reference the non-existent Python device)
    core3 = CMMCorePlus()
    with pytest.raises((OSError, RuntimeError)):
        core3.loadSystemConfiguration(str(save_path))
