"""Regression tests from the review of UniMMCore on the pymmcore-nano bridge.

Each test documents a behavior found to be incorrect or inconsistent with the
C++ MMCore/MMDevice semantics during review, and failed before the fixes.
"""

from __future__ import annotations

import types
from typing import TYPE_CHECKING

import numpy as np
import pytest

from pymmcore_plus.experimental.unicore import (
    GenericDevice,
    SimpleCameraDevice,
    UniMMCore,
    XYStepperStageDevice,
)
from pymmcore_plus.experimental.unicore.devices._properties import pymm_property

if TYPE_CHECKING:
    from collections.abc import Mapping


# ---------------------------------------------------------------------------
# 1. Color cameras: CameraDevice.get_bytes_per_pixel() returned the dtype
#    itemsize, ignoring components.  MM::Camera::GetImageBytesPerPixel() is the
#    *total* bytes per pixel (RGB32 cameras report 4, with 4 components), and
#    MMCore sizes every copy with GetImageBufferSize() == w*h*bytesPerPixel.
#    A (h, w, 3) uint8 camera therefore reports 1 byte/pixel: CMMCore copies
#    one third of the frame, getImage() returns a (h, w) gray image of
#    interleaved channel bytes, and sequence frames are tagged GRAY8.
#    (The pre-PR pure-Python UniMMCore returned the (h, w, 3) array intact.)
# ---------------------------------------------------------------------------


class ColorCam(SimpleCameraDevice):
    def get_exposure(self) -> float:
        return 10.0

    def set_exposure(self, v: float) -> None:
        pass

    def sensor_shape(self) -> tuple[int, int, int]:
        return (16, 16, 3)

    def dtype(self):
        return np.uint8

    def snap(self, buffer: np.ndarray) -> Mapping:
        buffer[..., 0] = 10
        buffer[..., 1] = 20
        buffer[..., 2] = 30
        return {}


def test_color_camera_frame_is_not_truncated() -> None:
    core = UniMMCore()
    core.loadPyDevice("Cam", ColorCam())
    core.initializeDevice("Cam")
    core.setCameraDevice("Cam")
    assert core.getImageBufferSize() >= 16 * 16 * 3
    core.snapImage()
    img = core.getImage()
    assert img.shape == (16, 16, 3)
    np.testing.assert_array_equal(img[..., 0], 10)
    np.testing.assert_array_equal(img[..., 1], 20)
    np.testing.assert_array_equal(img[..., 2], 30)

    # sequence frames go through the circular buffer with the full pixel size
    core.startSequenceAcquisition(2, 0, True)
    while core.isSequenceRunning():
        pass
    frame = core.popNextImage()
    assert frame.shape == (16, 16, 3)
    np.testing.assert_array_equal(frame[..., 2], 30)


# ---------------------------------------------------------------------------
# 2. Devices loaded through a registered Python adapter are instantiated by the
#    C++ bridge (PyBridgeAdapter::CreateDevice -> cls()).  Nothing told the
#    Python object its label: Device._label_ stayed "" and UniMMCore._pydevices
#    did not know about it, so get_label() was wrong, isPyDevice() was False,
#    setProperty() skipped Python-side validation, and getSLMImage() refused it.
# ---------------------------------------------------------------------------


class LabelReporter(GenericDevice):
    """Device exposing its own label as a property."""

    @pymm_property(is_read_only=True)
    def my_label(self) -> str:
        return self.get_label()


def test_adapter_loaded_device_knows_its_label() -> None:
    mod = types.ModuleType("fake_adapter_mod")
    mod.__pymmcore_devices__ = [LabelReporter]  # type: ignore[attr-defined]
    core = UniMMCore()
    core.register_py_adapter("FakeAdapter", mod)
    core.loadDevice("LD", "FakeAdapter", "LabelReporter")
    assert core.isPyDevice("LD")
    core.initializeDevice("LD")
    assert core.getProperty("LD", "my_label") == "LD"
    # Python-side validation applies to adapter-loaded devices too
    with pytest.raises(ValueError, match="read-only"):
        core.setProperty("LD", "my_label", "x")
    core.unloadDevice("LD")
    assert not core.isPyDevice("LD")


# ---------------------------------------------------------------------------
# 3. XYStepperStageDevice did not implement set_x_origin / set_y_origin, which
#    pymmcore_nano.protocols.PyXYStepperStage requires.  core.setOriginX()
#    failed with an AttributeError instead of a device error.
# ---------------------------------------------------------------------------


class Stepper(XYStepperStageDevice):
    _x = _y = 0

    def set_position_steps(self, x: int, y: int) -> None:
        self._x, self._y = x, y

    def get_position_steps(self) -> tuple[int, int]:
        return (self._x, self._y)

    def get_step_size_x_um(self) -> float:
        return 0.1

    def get_step_size_y_um(self) -> float:
        return 0.1

    def home(self) -> None:
        pass

    def stop(self) -> None:
        pass


def test_stepper_satisfies_bridge_protocol() -> None:
    from pymmcore_nano.protocols import PyXYStepperStage

    assert isinstance(Stepper(), PyXYStepperStage)


def test_stepper_set_origin_x_does_not_raise_attribute_error() -> None:
    core = UniMMCore()
    core.loadPyDevice("XY", Stepper())
    core.initializeDevice("XY")
    core.setXYStageDevice("XY")
    with pytest.raises(RuntimeError) as ei:
        core.setOriginX("XY")
    assert "AttributeError" not in str(ei.value)
