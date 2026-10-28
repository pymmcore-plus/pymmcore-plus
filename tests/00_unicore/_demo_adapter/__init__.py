"""Demo Python device adapter for testing.

Contains a camera and a Z stage, discoverable as a Python adapter module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from pymmcore_plus.experimental.unicore import SimpleCameraDevice, StageDevice

if TYPE_CHECKING:
    from collections.abc import Mapping


class DemoPyCam(SimpleCameraDevice):
    """A demo Python camera."""

    _exposure: float = 10.0

    def get_exposure(self) -> float:
        return self._exposure

    def set_exposure(self, v: float) -> None:
        self._exposure = v

    def sensor_shape(self) -> tuple[int, int]:
        return (64, 64)

    def dtype(self):
        return np.uint16

    def snap(self, buffer: np.ndarray) -> Mapping:
        buffer[:] = np.random.randint(0, 100, buffer.shape, dtype=buffer.dtype)
        return {}


class DemoPyStage(StageDevice):
    """A demo Python Z stage."""

    _pos: float = 0.0

    def set_position_um(self, val: float) -> None:
        self._pos = val

    def get_position_um(self) -> float:
        return self._pos

    def home(self) -> None:
        self._pos = 0.0

    def stop(self) -> None:
        pass

    def set_origin(self) -> None:
        self._pos = 0.0
