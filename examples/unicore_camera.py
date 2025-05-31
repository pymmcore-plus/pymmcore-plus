"""Example of using combined C and Python devices in UniCore.

Unicore is a subclass of MMCore that allows for loading Python devices, which must be
subclasses of `pymmcore_plus.unicore.Device`. The final API is unchanged from
CMMCorePlus: the Unicore knows whether a device label corresponds to a C++ or Python
device and routes the call accordingly.

This example demonstrates how to create a custom Python stage device and use it together
with other C++ devices.
"""

import time
from collections.abc import Iterator, Mapping
from typing import Callable

import numpy as np

from pymmcore_plus.experimental.unicore import Camera, UniMMCore

_START_TIME: float = time.time()


def make_cool_image(shape: tuple[int, int], dtype: np.typing.DTypeLike) -> np.ndarray:
    """Return a cool looking sinusoidal image with temporal correlations."""
    (nx, ny) = shape

    x = np.linspace(0, 2 * np.pi, ny, endpoint=False)
    y = np.linspace(0, 2 * np.pi, nx, endpoint=False)
    X, Y = np.meshgrid(x, y)

    # Time-dependent parameters for "breathing" and rotation
    # Breathing: slowly varying amplitude with period of ~5 seconds
    elapsed_time = time.time() - _START_TIME
    breathing_amplitude = 0.3 + 0.7 * (1 + np.sin(2 * np.pi * elapsed_time / 5.0)) / 2
    # Rotation: slow continuous rotation with period of ~8 seconds
    rotation_angle = 2 * np.pi * elapsed_time / 8.0
    # Additional phase shift for more complex temporal dynamics
    phase_shift = np.pi * elapsed_time / 3.0
    # Create base pattern with breathing amplitude
    image = breathing_amplitude * np.sin(X + phase_shift) * np.cos(Y + phase_shift)

    # Add rotated sine wave that slowly rotates over time
    # Apply rotation transformation
    X_rot = X * np.cos(rotation_angle) - Y * np.sin(rotation_angle)
    Y_rot = X * np.sin(rotation_angle) + Y * np.cos(rotation_angle)

    # Add the rotated component with different frequency
    secondary_amplitude = 0.4 + 0.3 * np.sin(2 * np.pi * elapsed_time / 7.0)
    image += secondary_amplitude * np.sin(1.5 * X_rot) * np.cos(1.2 * Y_rot)

    # Add subtle temporal noise for more organic feel
    noise_amplitude = 0.1 * np.sin(2 * np.pi * elapsed_time / 2.0)
    image += noise_amplitude * np.random.uniform(-0.1, 0.1, image.shape)

    # normalize to [0, 255] and convert to the specified dtype
    image = (image - image.min()) / (image.max() - image.min())
    image = (image * 255).astype(dtype)
    return image  # type: ignore[no-any-return]


class MyCamera(Camera):
    _exposure: float = 10.0
    _start_time: float = time.time()

    def get_exposure(self) -> float:
        return self._exposure

    def set_exposure(self, exposure: float) -> None:
        self._exposure = exposure

    def shape(self) -> tuple[int, int]:
        return (480, 640)

    def dtype(self) -> np.typing.DTypeLike:
        """Return the data type of the image buffer."""
        return np.uint8

    def start_sequence(
        self, n: int, get_buffer: Callable[[], np.ndarray]
    ) -> Iterator[Mapping]:
        """Start a sequence acquisition."""
        for _ in range(n):
            # Simulate image acquisition
            get_buffer()[:] = make_cool_image(self.shape(), self.dtype())
            yield {"timestamp": time.time()}  # any metadata


core = UniMMCore()
# core.loadSystemConfiguration()
core.loadPyDevice("Camera", MyCamera())
core.initializeDevice("Camera")
core.setCameraDevice("Camera")

core.setExposure(42.0)


try:
    from pymmcore_widgets import ImagePreview, LiveButton, SnapButton
    from qtpy.QtWidgets import QApplication, QVBoxLayout, QWidget

    app = QApplication([])

    window = QWidget()
    window.setWindowTitle("UniCore Camera Example")
    layout = QVBoxLayout(window)
    layout.addWidget(SnapButton(mmcore=core))
    layout.addWidget(LiveButton(mmcore=core))
    preview = ImagePreview(mmcore=core)
    preview.setMinimumSize(640, 480)
    layout.addWidget(preview)
    window.setLayout(layout)
    window.resize(800, 600)
    window.show()
    app.exec()
except Exception:
    print("run `pip install pymmcore-widgets[image]` to run the GUI example")
    core.snapImage()
    image = core.getImage()
    print("Image shape:", image.shape)
    print("Image dtype:", image.dtype)
    print("Image data:", image)
