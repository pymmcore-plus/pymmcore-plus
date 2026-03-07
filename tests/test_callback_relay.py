"""Tests for the callback relay architecture handling async C++ callbacks."""

from __future__ import annotations

import time
from unittest.mock import Mock

import pytest

from pymmcore_plus import CMMCorePlus


@pytest.fixture
def core() -> CMMCorePlus:
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    return core


def test_setConfig_no_double_propertyChanged(core: CMMCorePlus) -> None:
    """setConfig should not cause double propertyChanged emissions."""
    core.setConfig("Channel", "DAPI")
    time.sleep(0.3)

    seen: dict[tuple[str, str], str] = {}

    def track(dev: str, prop: str, val: str) -> None:
        key = (dev, prop)
        if key in seen:
            pytest.fail(f"propertyChanged({dev}, {prop}) emitted twice")
        seen[key] = val

    core.events.propertyChanged.connect(track)
    core.setConfig("Channel", "FITC")
    time.sleep(0.3)


def test_setProperty_emits_propertyChanged_once(core: CMMCorePlus) -> None:
    """setProperty should emit propertyChanged exactly once per change."""
    cam = core.getCameraDevice()
    current = core.getProperty(cam, "Exposure")
    new_val = "77.0" if current != "77.0" else "88.0"

    received: list[str] = []

    def track(dev: str, prop: str, val: str) -> None:
        if dev == cam and prop == "Exposure":
            received.append(val)

    core.events.propertyChanged.connect(track)
    core.setProperty(cam, "Exposure", new_val)
    time.sleep(0.2)

    assert len(received) == 1


def test_imageSnapped_emitted_once(core: CMMCorePlus) -> None:
    """imageSnapped should fire exactly once (RELAY_SKIP)."""
    mock = Mock()
    core.events.imageSnapped.connect(mock)
    core.snapImage()
    time.sleep(0.3)
    assert mock.call_count == 1


def test_setConfig_propertyChanged_arrives(core: CMMCorePlus) -> None:
    """Property changes from setConfig should not be over-suppressed."""
    core.setConfig("Channel", "DAPI")
    time.sleep(0.3)

    props: list[tuple[str, str, str]] = []
    core.events.propertyChanged.connect(lambda d, p, v: props.append((d, p, v)))

    core.setConfig("Channel", "FITC")
    time.sleep(0.3)

    assert len(props) > 0


def test_property_suppressed_nesting(core: CMMCorePlus) -> None:
    """Nested property_suppressed contexts use refcounting correctly."""
    cam = core.getCameraDevice()
    relay = core._callback_relay
    key = (cam, "Exposure")

    received: list[str] = []

    def track(dev: str, prop: str, val: str) -> None:
        if dev == cam and prop == "Exposure":
            received.append(val)

    core.events.propertyChanged.connect(track)

    with relay.property_suppressed(cam, ("Exposure",)):
        with relay.property_suppressed(cam, ("Exposure",)):
            relay.onPropertyChanged(cam, "Exposure", "1")
            assert relay._prop_suppressed[key] == 2

        relay.onPropertyChanged(cam, "Exposure", "2")
        assert relay._prop_suppressed[key] == 1

    relay.onPropertyChanged(cam, "Exposure", "3")
    assert key not in relay._prop_suppressed
    assert received == ["3"]
