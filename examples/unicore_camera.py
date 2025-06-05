"""Example of using combined C and Python devices in UniCore.

Unicore is a subclass of MMCore that allows for loading Python devices, which must be
subclasses of `pymmcore_plus.unicore.Device`. The final API is unchanged from
CMMCorePlus: the Unicore knows whether a device label corresponds to a C++ or Python
device and routes the call accordingly.

This example demonstrates how to create a custom Python camera device that generates
cool synthetic images.
"""

import time
from collections.abc import Iterator, Mapping, Sequence
from typing import Callable

import numpy as np
from numpy.typing import DTypeLike

from pymmcore_plus.experimental.unicore import Camera, UniMMCore

_START_TIME: float = time.time()


def make_cool_image(
    shape: tuple[int, int], dtype: DTypeLike, exposure_ms: float = 10.0
) -> np.ndarray:
    """Return a cool looking sinusoidal image with temporal correlations.


    Parameters
    ----------
    shape: tuple[int, int]
        The shape of the output image.
        The first element is the height (number of rows), the second is the width
        (number of columns).
    dtype: DTypeLike
        The data type of the output image.
    exposure_ms: float
        Exposure time in milliseconds. Shorter exposures result in noisier images.
        100ms gives very good SNR, 1ms is almost dominated by noise.
    """
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

    # Signal amplitude scales with exposure time (more photons = stronger signal)
    # Use square root relationship to simulate photon statistics
    signal_strength = np.sqrt(exposure_ms / 100.0)  # Normalized to 100ms reference

    # Create base pattern with breathing amplitude and exposure-dependent strength
    image = (
        signal_strength
        * breathing_amplitude
        * np.sin(X + phase_shift)
        * np.cos(Y + phase_shift)
    )

    # Add rotated sine wave that slowly rotates over time
    # Apply rotation transformation
    X_rot = X * np.cos(rotation_angle) - Y * np.sin(rotation_angle)
    Y_rot = X * np.sin(rotation_angle) + Y * np.cos(rotation_angle)

    # Add the rotated component with different frequency
    secondary_amplitude = 0.4 + 0.3 * np.sin(2 * np.pi * elapsed_time / 7.0)
    image += (
        signal_strength
        * secondary_amplitude
        * np.sin(1.5 * X_rot)
        * np.cos(1.2 * Y_rot)
    )

    # Add exposure-dependent noise
    # Shorter exposures have relatively more noise
    noise_std = 0.1 / np.sqrt(max(exposure_ms, 0.1))  # Avoid division by zero
    image += np.random.normal(0, noise_std, image.shape)

    # normalize to [0, 255] and convert to the specified dtype
    # Clip to avoid overflow from noise
    image = np.clip(image, image.min(), image.max())
    image = (image - image.min()) / (image.max() - image.min())
    image = (image * 255).astype(dtype)
    return image  # type: ignore[no-any-return]


class MyCamera(Camera):
    _exposure: float = 10.0

    def get_exposure(self) -> float:
        return self._exposure

    def set_exposure(self, exposure: float) -> None:
        self._exposure = exposure

    def shape(self) -> tuple[int, int]:
        return (480, 640)

    def dtype(self) -> DTypeLike:
        """Return the data type of the image buffer."""
        return np.uint8

    def start_sequence(
        self,
        n: int,
        get_buffer: Callable[[Sequence[int], DTypeLike], np.ndarray],
    ) -> Iterator[Mapping]:
        """Start a sequence acquisition."""
        for _ in range(n):
            # Simulate image acquisition with current exposure time
            time.sleep(self._exposure / 1000.0)  # Convert ms to seconds
            buf = get_buffer(self.shape(), self.dtype())
            buf[:] = make_cool_image(self.shape(), self.dtype(), self._exposure)
            yield {"timestamp": time.time()}  # any metadata


core = UniMMCore()
# core.loadSystemConfiguration()
core.loadPyDevice("Camera", MyCamera())
core.initializeDevice("Camera")
core.setCameraDevice("Camera")

core.setExposure(42)


try:
    from pymmcore_widgets import ExposureWidget, ImagePreview, LiveButton, SnapButton
    from qtpy.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget

    app = QApplication([])

    window = QWidget()
    window.setWindowTitle("UniCore Camera Example")
    layout = QVBoxLayout(window)

    top = QHBoxLayout()
    top.addWidget(SnapButton(mmcore=core))
    top.addWidget(LiveButton(mmcore=core))
    top.addWidget(ExposureWidget(mmcore=core))
    layout.addLayout(top)
    layout.addWidget(ImagePreview(mmcore=core))
    window.setLayout(layout)
    window.resize(800, 600)
    window.show()
    app.exec()
except Exception:
    print("run `pip install pymmcore-widgets[image] PyQt6` to run the GUI example")
    core.snapImage()
    image = core.getImage()
    print("Image shape:", image.shape)
    print("Image dtype:", image.dtype)
    print("Image data:", image)
