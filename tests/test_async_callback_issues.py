"""Tests for the callback relay architecture handling async C++ callbacks.

MMCore v12 (https://github.com/micro-manager/mmCoreAndDevices/pull/877) changed
all MMEventCallback calls from synchronous (inline on the device thread) to
asynchronous (posted to a NotificationQueue, delivered on a dedicated thread).

The relay architecture uses three strategies:
1. RELAY_SKIP — CMMCorePlus method is sole emitter; relay drops C++ callback
2. RELAY_ONLY — C++ callback is sole source; no manual emission exists
3. CUSTOM_RELAY — Value-aware dedup for propertyChanged
"""

from __future__ import annotations

import threading
import time
from unittest.mock import Mock

import pytest

from pymmcore_plus import CMMCorePlus


@pytest.fixture
def core() -> CMMCorePlus:
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    return core


# ---------------------------------------------------------------------------
# channelGroupChanged: RELAY_SKIP — only manual emission
# ---------------------------------------------------------------------------


def test_setChannelGroup_no_double_emission(core: CMMCorePlus) -> None:
    """setChannelGroup should emit channelGroupChanged exactly once."""
    core.setChannelGroup("Camera")
    time.sleep(0.2)

    calls: list[tuple[str, int]] = []

    def track(name: str) -> None:
        calls.append((name, threading.current_thread().ident))

    core.events.channelGroupChanged.connect(track)

    core.setChannelGroup("Channel")
    time.sleep(0.3)

    assert len(calls) == 1, (
        f"channelGroupChanged emitted {len(calls)} times, expected 1. Calls: {calls}"
    )


def test_channelGroupChanged_thread_consistency(core: CMMCorePlus) -> None:
    """All channelGroupChanged emissions should be on the same thread."""
    core.setChannelGroup("Camera")
    time.sleep(0.2)

    threads: list[int] = []

    def track(name: str) -> None:
        threads.append(threading.current_thread().ident)

    core.events.channelGroupChanged.connect(track)

    core.setChannelGroup("Channel")
    time.sleep(0.3)

    unique_threads = set(threads)
    assert len(unique_threads) <= 1, (
        f"channelGroupChanged emitted from {len(unique_threads)} different "
        f"threads: {unique_threads}."
    )


# ---------------------------------------------------------------------------
# propertyChanged: CUSTOM_RELAY — value-aware dedup
# ---------------------------------------------------------------------------


def test_setConfig_does_not_double_emit_propertyChanged(
    core: CMMCorePlus,
) -> None:
    """setConfig should not cause double propertyChanged emissions."""
    core.setConfig("Channel", "DAPI")
    time.sleep(0.3)

    calls: list[tuple[str, str, str]] = []

    def track(dev: str, prop: str, val: str) -> None:
        calls.append((dev, prop, val))

    core.events.propertyChanged.connect(track)

    core.setConfig("Channel", "FITC")
    time.sleep(0.3)

    seen: dict[tuple[str, str], str] = {}
    for dev, prop, val in calls:
        key = (dev, prop)
        if key in seen:
            pytest.fail(
                f"propertyChanged({dev}, {prop}) emitted multiple times: "
                f"first with val={seen[key]}, then val={val}"
            )
        seen[key] = val


def test_setProperty_emits_propertyChanged_for_all_changes(
    core: CMMCorePlus,
) -> None:
    """Every setProperty call that changes a value should emit exactly once."""
    cam = core.getCameraDevice()
    current = core.getProperty(cam, "Exposure")

    values_received: list[str] = []

    def track(dev: str, prop: str, val: str) -> None:
        if dev == cam and prop == "Exposure":
            values_received.append(val)

    core.events.propertyChanged.connect(track)

    new_val = "77.0" if current != "77.0" else "88.0"
    core.setProperty(cam, "Exposure", new_val)
    time.sleep(0.2)

    assert len(values_received) == 1, (
        f"Expected 1 propertyChanged for Exposure, got {len(values_received)}: "
        f"{values_received}"
    )


# ---------------------------------------------------------------------------
# snapImage: string values for propertyChanged
# ---------------------------------------------------------------------------


def test_snapImage_shutter_propertyChanged_types(core: CMMCorePlus) -> None:
    """snapImage should emit propertyChanged with string values, not bools."""
    core.setAutoShutter(True)

    calls: list[tuple] = []

    def track(dev: str, prop: str, val: str) -> None:
        calls.append((dev, prop, val, type(val).__name__))

    core.events.propertyChanged.connect(track)
    core.snapImage()
    time.sleep(0.2)

    for dev, prop, val, type_name in calls:
        assert type_name == "str", (
            f"propertyChanged({dev}, {prop}, {val!r}) emitted with "
            f"type {type_name}, expected str"
        )


# ---------------------------------------------------------------------------
# RELAY_SKIP: imageSnapped still works
# ---------------------------------------------------------------------------


def test_skip_mechanism_prevents_duplicate_imageSnapped(
    core: CMMCorePlus,
) -> None:
    """imageSnapped should be emitted exactly once (via manual emit, not relay)."""
    mock = Mock()
    core.events.imageSnapped.connect(mock)

    core.snapImage()
    time.sleep(0.3)

    assert mock.call_count == 1, (
        f"imageSnapped emitted {mock.call_count} times, expected 1"
    )


# ---------------------------------------------------------------------------
# Dedup: simulated device that fires onPropertyChanged from C++
# ---------------------------------------------------------------------------


def test_simulated_device_onPropertyChanged_dedup(
    core: CMMCorePlus,
) -> None:
    """A C++ callback matching a manual emission should be deduped."""
    cam = core.getCameraDevice()
    current = core.getProperty(cam, "Exposure")

    calls: list[tuple[str, str, str]] = []

    def track(dev: str, prop: str, val: str) -> None:
        if dev == cam and prop == "Exposure":
            calls.append((dev, prop, val))

    core.events.propertyChanged.connect(track)

    new_val = "77.0" if current != "77.0" else "88.0"

    # setProperty uses _property_change_emission_ensured, which registers a
    # dedup token then emits manually
    core.setProperty(cam, "Exposure", new_val)

    # The token is registered with the device-returned value format
    device_val = core.getProperty(cam, "Exposure")

    # Simulate what happens when the device adapter also fires
    # OnPropertyChanged from C++ with the same value (device format)
    core._callback_relay.onPropertyChanged(cam, "Exposure", device_val)

    time.sleep(0.1)

    assert len(calls) == 1, f"Expected 1 emission (deduped), got {len(calls)}: {calls}"


def test_hardware_initiated_change_relays_through(
    core: CMMCorePlus,
) -> None:
    """A C++ callback with a different value should NOT be deduped."""
    cam = core.getCameraDevice()
    current = core.getProperty(cam, "Exposure")

    calls: list[tuple[str, str, str]] = []

    def track(dev: str, prop: str, val: str) -> None:
        if dev == cam and prop == "Exposure":
            calls.append((dev, prop, val))

    core.events.propertyChanged.connect(track)

    new_val = "77.0" if current != "77.0" else "88.0"
    hw_val = "99.0"  # different value — simulates hardware-initiated change

    core.setProperty(cam, "Exposure", new_val)
    device_val = core.getProperty(cam, "Exposure")

    # Simulate hardware firing with a DIFFERENT value
    core._callback_relay.onPropertyChanged(cam, "Exposure", hw_val)

    time.sleep(0.1)

    assert len(calls) == 2, (
        f"Expected 2 emissions (manual + hardware), got {len(calls)}: {calls}"
    )
    assert calls[0][2] == device_val
    assert calls[1][2] == hw_val


# ---------------------------------------------------------------------------
# Rapid same-property writes: queue-based dedup
# ---------------------------------------------------------------------------


def test_rapid_same_property_writes(core: CMMCorePlus) -> None:
    """Rapid writes to the same property should each emit exactly once."""
    cam = core.getCameraDevice()

    calls: list[str] = []

    def track(dev: str, prop: str, val: str) -> None:
        if dev == cam and prop == "Exposure":
            calls.append(val)

    core.events.propertyChanged.connect(track)

    values = ["55.0", "66.0", "77.0"]
    expected: list[str] = []
    for v in values:
        core.setProperty(cam, "Exposure", v)
        device_val = core.getProperty(cam, "Exposure")
        expected.append(device_val)
        # Simulate C++ async callback for each (using device-format value)
        core._callback_relay.onPropertyChanged(cam, "Exposure", device_val)

    time.sleep(0.2)

    assert calls == expected, (
        f"Expected exactly {expected}, got {calls}. "
        "Dedup queue may have consumed wrong tokens."
    )


# ---------------------------------------------------------------------------
# Token expiry: stale tokens don't suppress future callbacks
# ---------------------------------------------------------------------------


def test_dedup_token_expiry(core: CMMCorePlus) -> None:
    """Expired tokens should not suppress future callbacks."""
    from pymmcore_plus.core._mmcore_plus import _DEDUP_TTL

    cam = core.getCameraDevice()
    relay = core._callback_relay

    # Register a token manually then expire it
    relay.register_property_emission(cam, "Exposure", "42.0")

    # Manually expire it by adjusting the stored expiry
    key = (cam, "Exposure")
    with relay._lock:
        tokens = relay._prop_drop_tokens[key]
        # Set expiry to the past
        tokens[0] = (tokens[0][0], time.monotonic() - _DEDUP_TTL - 1)

    calls: list[str] = []

    def track(dev: str, prop: str, val: str) -> None:
        if dev == cam and prop == "Exposure":
            calls.append(val)

    core.events.propertyChanged.connect(track)

    # This should relay through because the token is expired
    relay.onPropertyChanged(cam, "Exposure", "42.0")

    assert len(calls) == 1, f"Expected 1 emission (expired token), got {len(calls)}"
    assert calls[0] == "42.0"


# ---------------------------------------------------------------------------
# setConfig property changes still arrive via relay
# ---------------------------------------------------------------------------


def test_setConfig_property_changes_arrive(core: CMMCorePlus) -> None:
    """Property changes from setConfig should arrive (via relay or manual)."""
    core.setConfig("Channel", "DAPI")
    time.sleep(0.3)

    props: list[tuple[str, str, str]] = []

    def track(dev: str, prop: str, val: str) -> None:
        props.append((dev, prop, val))

    core.events.propertyChanged.connect(track)

    core.setConfig("Channel", "FITC")
    time.sleep(0.3)

    # At minimum, some property changes should have arrived
    assert len(props) > 0, "No propertyChanged events from setConfig"
