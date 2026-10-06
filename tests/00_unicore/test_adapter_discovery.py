"""Tests for Python device adapter discovery and registration."""

from __future__ import annotations

import importlib
from importlib.metadata import EntryPoint
from unittest.mock import patch

import numpy as np

from pymmcore_plus.experimental.unicore.core._adapter_discovery import (
    scan_module_for_devices,
)
from pymmcore_plus.experimental.unicore.core._unicore import UniMMCore

ADAPTER_NAME = "DemoPyAdapter"
# The 00_unicore directory can't be a normal Python import path (starts with
# digit), but importlib.import_module handles it fine via sys.path.
MODULE_PATH = "tests.00_unicore._demo_adapter"

_demo_mod = importlib.import_module(MODULE_PATH)


def _mock_entry_points(**kwargs):
    """Return a mock entry point pointing to our test adapter."""
    return [
        EntryPoint(
            name=ADAPTER_NAME,
            value=MODULE_PATH,
            group="pymmcore-plus.adapters",
        )
    ]


def test_scan_module_for_devices():
    """scan_module_for_devices finds concrete Device subclasses."""
    classes = scan_module_for_devices(_demo_mod)
    names = {cls.__name__ for cls in classes}
    assert "DemoPyCam" in names
    assert "DemoPyStage" in names
    assert len(classes) == 2


def test_scan_module_respects_explicit_list():
    """If __pymmcore_devices__ is defined, only those classes are returned."""
    DemoPyCam = _demo_mod.DemoPyCam

    original = getattr(_demo_mod, "__pymmcore_devices__", None)
    try:
        _demo_mod.__pymmcore_devices__ = [DemoPyCam]
        classes = scan_module_for_devices(_demo_mod)
        assert classes == [DemoPyCam]
    finally:
        if original is None:
            delattr(_demo_mod, "__pymmcore_devices__")
        else:
            _demo_mod.__pymmcore_devices__ = original


def test_register_py_adapter():
    """Explicit registration makes devices available through CMMCore API."""
    core = UniMMCore()
    core.register_py_adapter(ADAPTER_NAME, MODULE_PATH)

    # Adapter appears in adapter names
    assert ADAPTER_NAME in core.getDeviceAdapterNames()

    # Devices are discoverable
    devices = core.getAvailableDevices(ADAPTER_NAME)
    assert "DemoPyCam" in devices
    assert "DemoPyStage" in devices

    descriptions = core.getAvailableDeviceDescriptions(ADAPTER_NAME)
    assert "A demo Python camera." in descriptions
    assert "A demo Python Z stage." in descriptions

    # Load and use a camera through the standard string-based API
    core.loadDevice("Cam", ADAPTER_NAME, "DemoPyCam")
    core.initializeDevice("Cam")
    core.setCameraDevice("Cam")

    core.snapImage()
    img = core.getImage()
    assert img.shape == (64, 64)
    assert img.dtype == np.uint16

    # Device info comes from C++ (not the _pydevices override path)
    assert core.getDeviceName("Cam") == "DemoPyCam"
    assert core.getDeviceLibrary("Cam") == ADAPTER_NAME
    assert core.getDeviceDescription("Cam") == "A demo Python camera."

    # Load and use a stage
    core.loadDevice("Z", ADAPTER_NAME, "DemoPyStage")
    core.initializeDevice("Z")
    core.setFocusDevice("Z")

    core.setPosition(100.0)
    assert core.getPosition() == 100.0


@patch(
    "pymmcore_plus.experimental.unicore.core._adapter_discovery.importlib.metadata.entry_points",
    side_effect=_mock_entry_points,
)
def test_entry_point_discovery(_mock):
    """Entry point adapters appear in getDeviceAdapterNames and load lazily."""
    core = UniMMCore()

    # Adapter is visible before any device is loaded
    assert ADAPTER_NAME in core.getDeviceAdapterNames()

    # Loading a device triggers lazy registration
    core.loadDevice("Cam", ADAPTER_NAME, "DemoPyCam")
    core.initializeDevice("Cam")
    core.setCameraDevice("Cam")

    core.snapImage()
    assert core.getImage().shape == (64, 64)


@patch(
    "pymmcore_plus.experimental.unicore.core._adapter_discovery.importlib.metadata.entry_points",
    side_effect=_mock_entry_points,
)
def test_get_available_devices_triggers_lazy_load(_mock):
    """Querying available devices triggers lazy adapter registration."""
    core = UniMMCore()

    devices = core.getAvailableDevices(ADAPTER_NAME)
    assert "DemoPyCam" in devices
    assert "DemoPyStage" in devices


def test_legacy_fallback_still_works():
    """Direct module import path still works without entry points."""
    core = UniMMCore()

    # Load using module.class pattern (no adapter registration)
    core.loadDevice("Cam", MODULE_PATH, "DemoPyCam")
    core.initializeDevice("Cam")
    core.setCameraDevice("Cam")

    core.snapImage()
    assert core.getImage().shape == (64, 64)
