from abc import abstractmethod
from collections.abc import Sequence
from typing import ClassVar, Literal

import numpy as np
from numpy.typing import DTypeLike

from pymmcore_plus.core._constants import DeviceType

from ._device_base import SequenceableDevice


class SLMDevice(SequenceableDevice[np.ndarray]):
    """ABC for Spatial Light Modulator (SLM) devices.

    SLM devices are capable of displaying images.  They are expected to represent a
    rectangular grid of pixels that can be either 8-bit or 32-bit.  Illumination (light
    source on or off) is logically independent of displaying the image.
    """

    _TYPE: ClassVar[Literal[DeviceType.SLM]] = DeviceType.SLM

    @abstractmethod
    def shape(self) -> tuple[int, ...]:
        """Return the shape of the SLM image buffer.

        This is used when querying Width, Height, *and* number of components.
        If the SLM is grayscale, it should return (width, height).
        If the SLM is color, it should return (width, height, n_channels).
        """
        ...

    @abstractmethod
    def dtype(self) -> DTypeLike:
        """Return the data type of the image buffer."""
        ...

    @abstractmethod
    def set_image(self, pixels: np.ndarray) -> None:
        """Load the image into the SLM device adapter."""
        ...

    def get_image(self) -> np.ndarray:
        """Get the current image from the SLM device adapter.

        This is useful for verifying that the image was set correctly.
        """
        raise NotImplementedError("This SLM device does not support getting images.")

    @abstractmethod
    def display_image(self) -> None:
        """Command the SLM to display the loaded image."""

    @abstractmethod
    def set_exposure(self, interval_ms: float) -> None:
        """Command the SLM to turn off after a specified interval."""
        ...

    @abstractmethod
    def get_exposure(self) -> float:
        """Find out the exposure interval of an SLM."""
        ...

    # Sequence methods from SequenceableDevice
    def get_sequence_max_length(self) -> int:
        """Return the maximum length of an image sequence that can be uploaded."""
        return 0  # Override in subclasses that support sequencing

    def send_sequence(self, sequence: Sequence[np.ndarray]) -> None:
        """Load a sequence of images to the SLM."""
        # Default implementation - override in subclasses that support sequencing
        raise NotImplementedError("This SLM device does not support sequences.")

    def start_sequence(self) -> None:
        """Start a sequence of images on the SLM."""
        # Default implementation - override in subclasses that support sequencing
        raise NotImplementedError("This SLM device does not support sequences.")

    def stop_sequence(self) -> None:
        """Stop a sequence of images on the SLM."""
        # Default implementation - override in subclasses that support sequencing
        raise NotImplementedError("This SLM device does not support sequences.")
