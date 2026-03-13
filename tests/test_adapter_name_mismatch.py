"""Regression test for adapter_name mismatch in Device.update_from_core.

Some device adapters (e.g. the Thorlabs TSI camera adapter) report a different
internal device name via core.getDeviceName() than the name required by
core.loadDevice()/core.getAvailableDevices(). This test ensures that
Device.update_from_core() detects and corrects such mismatches, so that
saved configuration files remain loadable.
"""

from __future__ import annotations

from unittest.mock import patch

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.model import Device, Microscope
from pymmcore_plus.model._device import DEVICE_GETTERS


def _make_bad_getters():
    """Return a copy of DEVICE_GETTERS where adapter_name returns a fake name."""
    bad = dict(DEVICE_GETTERS)

    def _bad_get_device_name(core, label):
        real = core.getDeviceName(label)
        if real == "DCam":
            return "DCam_Internal"  # simulates the TSI mismatch
        return real

    bad["adapter_name"] = _bad_get_device_name
    return bad


def test_adapter_name_mismatch_corrected() -> None:
    """Device.update_from_core keeps original adapter_name when core reports an unloadable name."""
    core = CMMCorePlus()
    core.loadSystemConfiguration()  # loads DemoCamera config

    # Create a Device with the correct adapter_name (as parsed from a .cfg file)
    dev = Device(name="Camera", library="DemoCamera", adapter_name="DCam")

    # Patch DEVICE_GETTERS so that "adapter_name" returns a name NOT in
    # getAvailableDevices - simulating the TSI adapter bug.
    bad_getters = _make_bad_getters()
    with patch.dict("pymmcore_plus.model._device.DEVICE_GETTERS", bad_getters):
        dev.update_from_core(core)

    # The fix should have detected that "DCam_Internal" is not in
    # getAvailableDevices("DemoCamera") and reverted to "DCam"
    assert dev.adapter_name == "DCam", (
        f"Expected adapter_name='DCam' but got {dev.adapter_name!r}. "
        f"update_from_core should keep the original adapter_name when "
        f"getDeviceName() returns a name not in getAvailableDevices()."
    )


def test_adapter_name_normal_update() -> None:
    """Device.update_from_core works normally when adapter names are consistent."""
    core = CMMCorePlus()
    core.loadSystemConfiguration()

    dev = Device(name="Camera", library="DemoCamera", adapter_name="DCam")
    dev.update_from_core(core)

    # Normal case: getDeviceName returns "DCam" which IS in getAvailableDevices
    assert dev.adapter_name == "DCam"


def test_adapter_name_empty_preserved() -> None:
    """When adapter_name starts empty, update_from_core still sets it from core."""
    core = CMMCorePlus()
    core.loadSystemConfiguration()

    # Simulate Device.create_from_core where adapter_name starts empty
    dev = Device(name="Camera")
    dev.update_from_core(core)

    # Should have been populated from the core
    assert dev.adapter_name == "DCam"


def test_model_roundtrip_with_mismatch(tmp_path) -> None:
    """A Microscope model with a mismatched adapter saves a loadable config."""
    core = CMMCorePlus()
    core.loadSystemConfiguration()

    # Build model from config (correct adapter_name)
    model = Microscope.create_from_core(core)
    cam = next(d for d in model.devices if d.name == "Camera")
    assert cam.adapter_name == "DCam"

    # Simulate what happens when ConfigWizard re-initializes devices.
    # Patch DEVICE_GETTERS to return the wrong adapter_name.
    bad_getters = _make_bad_getters()
    with patch.dict("pymmcore_plus.model._device.DEVICE_GETTERS", bad_getters):
        model.initialize(core, on_fail=lambda d, e: None)

    # adapter_name should still be correct
    cam = next(d for d in model.devices if d.name == "Camera")
    assert cam.adapter_name == "DCam"

    # Save and reload to verify the config is valid
    cfg_path = tmp_path / "test_output.cfg"
    model.save(cfg_path)
    cfg_text = cfg_path.read_text()
    assert "DCam_Internal" not in cfg_text, (
        "Saved config contains the wrong adapter name 'DCam_Internal'"
    )
    assert "Device,Camera,DemoCamera,DCam" in cfg_text
