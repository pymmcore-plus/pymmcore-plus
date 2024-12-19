from abc import abstractmethod
from typing import ClassVar, Literal

import numpy as np

from pymmcore_plus.core._constants import DeviceType

from ._device import SequenceableDevice


class SLMDevice(SequenceableDevice[np.ndarray]):
    """ABC for Spatial Light Modulator (SLM) devices.

    SLM devices are capable of displaying images.  They are expected to represent a
    rectangular grid of pixels that can be either 8-bit or 32-bit.  Illumination (light
    source on or off) is logically independent of displaying the image.
    """

    _TYPE: ClassVar[Literal[DeviceType.SLM]] = DeviceType.SLM

    @abstractmethod
    def get_width(self) -> int:
        """Get the SLM width in pixels."""

    @abstractmethod
    def get_height(self) -> int:
        """Get the SLM height in pixels."""

    @abstractmethod
    def get_bytes_per_pixel(self) -> int:
        """Get the SLM number of bytes per pixel."""

    def set_image(self, pixels: np.ndarray) -> None:
        """Load the image into the SLM device adapter."""
        raise NotImplementedError

    def display_image(self) -> None:
        """Command the SLM to display the loaded image."""
        raise NotImplementedError

    def set_pixels_to(self, intensity: int) -> None:
        """Command the SLM to display one 8-bit intensity."""
        raise NotImplementedError

    def set_pixels_to_rgb(self, red: int, green: int, blue: int) -> None:
        """Command the SLM to display one 32-bit color."""
        raise NotImplementedError

    def set_exposure(self, interval_ms: float) -> None:
        """Command the SLM to turn off after a specified interval."""
        raise NotImplementedError

    def get_exposure(self) -> float:
        """Find out the exposure interval of an SLM."""
        raise NotImplementedError

    def get_number_of_components(self) -> int:
        """Get the SLM number of components (colors)."""
        raise NotImplementedError
