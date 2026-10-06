"""Failing tests for review findings against nano-unicore-fixes3 (833dfb1).

Each test reproduces one defect. They are expected to FAIL on 833dfb1 (with
pymmcore-nano unicore-fixes3) and to pass once the issue is fixed.
"""

from __future__ import annotations

import sys
import time
import types

import pytest

from pymmcore_plus.core import DeviceType
from pymmcore_plus.experimental.unicore import (
    GenericDevice,
    HubDevice,
    UniMMCore,
    XYStepperStageDevice,
    pymm_property,
)

# ---------------------------------------------------------------------------
# U1. UniMMCore.loadDevice() masks any load error from a registered Python
#     adapter: `moduleName not in super().getDeviceAdapterNames()` is always
#     true for a mock adapter (CMMCore lists adapter *files*), so it falls back
#     to importing a Python module named after the adapter and raises
#     ModuleNotFoundError instead of the device's own error.
# ---------------------------------------------------------------------------


def _make_module() -> types.ModuleType:
    mod = types.ModuleType("review_badmod")

    class Broken(GenericDevice):
        """Broken device."""

        def __init__(self) -> None:
            super().__init__()
            raise ValueError("serial port COM7 not found")

    Broken.__module__ = mod.__name__
    mod.Broken = Broken  # type: ignore[attr-defined]
    return mod


def test_registered_adapter_load_error_is_not_masked() -> None:
    mod = _make_module()
    sys.modules[mod.__name__] = mod
    try:
        core = UniMMCore()
        core.register_py_adapter("ReviewAdapter", mod)
        with pytest.raises(Exception) as exc_info:
            core.loadDevice("D", "ReviewAdapter", "Broken")
        assert not isinstance(exc_info.value, ImportError)
        assert "COM7" in str(exc_info.value)
    finally:
        sys.modules.pop(mod.__name__, None)


# ---------------------------------------------------------------------------
# U2. A stepper XY stage reports isXYStageUsingCallbacks() == True (so a UI
#     will not poll it), but origin changes and home() change the reported
#     position without any XYStagePositionChanged notification.
# ---------------------------------------------------------------------------


class _Stepper(XYStepperStageDevice):
    def __init__(self) -> None:
        super().__init__()
        self.steps = [100, 200]

    def set_position_steps(self, x: int, y: int) -> None:
        self.steps = [x, y]

    def get_position_steps(self) -> tuple[int, int]:
        return (self.steps[0], self.steps[1])

    def get_step_size_x_um(self) -> float:
        return 0.5

    def get_step_size_y_um(self) -> float:
        return 0.5

    def home(self) -> None:
        self.steps = [0, 0]

    def stop(self) -> None:
        pass


@pytest.mark.parametrize("call", ["setOriginXY", "setAdapterOriginXY", "home"])
def test_stepper_using_callbacks_notifies_position_changes(call: str) -> None:
    core = UniMMCore()
    core.loadPyDevice("XY", _Stepper())
    core.initializeDevice("XY")
    core.setXYStageDevice("XY")
    core.setXYPosition(10.0, 20.0)
    assert core.isXYStageUsingCallbacks("XY")
    time.sleep(0.2)  # MMCore delivers notifications asynchronously

    events: list[tuple] = []
    core.events.XYStagePositionChanged.connect(lambda *a: events.append(a))
    before = core.getXYPosition("XY")
    if call == "setAdapterOriginXY":
        core.setAdapterOriginXY("XY", 5.0, 5.0)
    elif call == "home":
        core.home("XY")
    else:
        core.setOriginXY("XY")
    after = core.getXYPosition("XY")
    assert before != after
    time.sleep(0.3)
    assert events, f"{call} moved the stage {before} -> {after} without a callback"


# ---------------------------------------------------------------------------
# U3. A peripheral instance reported by a hub: each detection builds a new
#     prototype bridge around the same instance, which re-runs
#     create_pre_init_properties() and replaces the loaded device's
#     PropertyHandle with the prototype's.  Python and the core then disagree.
# ---------------------------------------------------------------------------


class _Motor(GenericDevice):
    """motor"""

    def __init__(self) -> None:
        super().__init__()
        self._port = "A"

    @pymm_property(is_pre_init=True, allowed_values=["A", "B"])
    def port(self) -> str:
        return self._port

    @port.setter
    def port(self, v: str) -> None:
        self._port = v


class _Hub(HubDevice):
    """hub"""

    def __init__(self) -> None:
        super().__init__()
        self.motor = _Motor()

    def detect_installed_devices(self):
        return [("M", self.motor, DeviceType.Generic)]


def test_hub_instance_pre_init_handles_survive_detection() -> None:
    core = UniMMCore()
    hub = _Hub()
    core.loadPyDevice("H", hub)
    lib = core.getDeviceLibrary("H")
    core.loadDevice("X", lib, "M")  # configuration-file order
    core.initializeDevice("H")
    core.initializeDevice("X")
    core.getInstalledDevices("H")

    hub.motor.set_property_allowed_values("port", ["A", "B", "C"])
    assert "C" in core.getAllowedPropertyValues("X", "port")
