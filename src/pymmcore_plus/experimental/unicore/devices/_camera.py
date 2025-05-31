from __future__ import annotations

import threading
from abc import abstractmethod
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, ClassVar

from pymmcore_plus.core._constants import Keyword, PixelFormat

from ._device import Device

if TYPE_CHECKING:
    from collections.abc import Mapping

    import numpy as np
    from numpy.typing import DTypeLike


class Camera(Device):
    # mandatory methods for Camera device adapters

    @abstractmethod
    def get_exposure(self) -> float:
        """Get the current exposure time in milliseconds."""
        ...

    @abstractmethod
    def set_exposure(self, exposure: float) -> None:
        """Set the exposure time in milliseconds."""
        ...

    @abstractmethod
    def shape(self) -> tuple[int, int]:
        """Return the shape of the image buffer.

        This is used when querying Width, Height, *and* number of components.
        If the camera is grayscale, it should return (width, height).
        If the camera is color, it should return (width, height, n_channels).
        """

    @abstractmethod
    def dtype(self) -> DTypeLike:
        """Return the data type of the image buffer."""

    @abstractmethod
    def start_sequence(
        self,
        n: int,
        get_buffer: Callable[[], np.ndarray],
        notify: Callable[[Mapping], None],
    ) -> None:
        """Start a sequence acquisition.

        This method should be implemented by the camera device adapter. It needn't worry
        about threading or synchronization; it may block and the core will handle
        threading and synchronization, though you may reimplement
        `start_sequence_thread` if you'd like to handle threading yourself.

        Parameters
        ----------
        n : int
            The number of images to acquire.
        get_buffer : Callable[[], np.ndarray]
            A callable that returns a buffer to be filled with the image data.
            The buffer will be a numpy array with the shape and dtype
            returned by `shape()` and `dtype()`.
            The point here is that the core creates the buffer, and the device adapter
            should just mutate it in place with the image data.
        notify : Callable[[Mapping], None]
            A callable that should be called with a mapping of metadata
            after the buffer has been filled with image data.
        """
        # EXAMPLE USAGE:
        for _ in range(n):
            image = get_buffer()

            # you MAY call get buffer multiple times before calling notify
            # ... however, you must call notify the same number of times that
            # you call get_buffer.  And semantically, each call to notify means
            # that the buffer corresponding to the first unresolved call to get_buffer
            # is now ready to be used.
            # image2 = get_buffer()

            # get the image from the camera, and fill the buffer in place
            image[:] = ...
            # image2[:] = ...

            # notify the core that the buffer is ready
            # the number of times you call notify must match the number of
            # times you call get_buffer ... and order must be the same
            # Calling `notify` more times than `get_buffer` results in a RuntimeError.
            notify({})
            # notify({})

            # TODO:
            # Open question: who is responsible for key pieces of metadata?
            # in CMMCore, each of the camera device adapters is responsible for
            # injecting to following bits of metadata:
            # - MM::g_Keyword_Metadata_CameraLabel
            # - MM::g_Keyword_Elapsed_Time_ms (GetCurrentMMTime - start_time)
            # - MM::g_Keyword_Metadata_ROI_X
            # - MM::g_Keyword_Metadata_ROI_Y
            # - MM::g_Keyword_Binning
            # --- while the CircularBuffer InsertMultiChannel is responsible for adding:
            # - MM::g_Keyword_Metadata_ImageNumber
            # - MM::g_Keyword_Elapsed_Time_ms
            # - MM::g_Keyword_Metadata_TimeInCore
            # - MM::g_Keyword_Metadata_Width
            # - MM::g_Keyword_Metadata_Height
            # - MM::g_Keyword_PixelType

    # Standard Properties --------------------------------------------

    # these are the standard properties that cameras may implement.
    # Cameras are not required to implement all of these properties, and they may
    # implement additional properties as well.
    # To implement a property, you MUST define a `get_<snake_name>` method and
    # MAY define a `set_<snake_name>` method.
    # To modify the standard properties, you can use the following methods in your
    # __init__, (after calling super().__init__()):
    # self.set_property_value(name, ...)
    # self.set_property_allowed_values(name, ...)
    # self.set_property_limits(name, ...)
    # self.set_property_sequence_max_length(name, ...)

    STANDARD_PROPERTIES: ClassVar = MappingProxyType(
        {
            Keyword.ActualInterval_ms: ("actual_interval_ms", float),
            Keyword.Binning: ("binning", int),
            Keyword.CameraID: ("camera_id", str),
            Keyword.CameraName: ("camera_name", str),
            Keyword.CCDTemperature: ("ccd_temperature", float),
            Keyword.CCDTemperatureSetPoint: ("ccd_temperature_set_point", float),
            Keyword.EMGain: ("em_gain", float),
            Keyword.Exposure: ("exposure", float),
            Keyword.Gain: ("gain", float),
            Keyword.Interval_ms: ("interval_ms", float),
            Keyword.Offset: ("offset", float),
            # Keyword.PixelType: ("pixel_type", str),  # don't use.  use PixelFormat
            "PixelFormat": ("pixel_format", PixelFormat),
            Keyword.ReadoutMode: ("readout_mode", str),
            Keyword.ReadoutTime: ("readout_time", float),
        }
    )

    # optional methods
    # def get_camera_name(self) -> str:
    # def set_camera_name(self, value: str) -> None:
    # def get_camera_id(self) -> str:
    # def set_camera_id(self, value: str) -> None:
    # def get_binning(self) -> str:
    # def set_binning(self, value: str) -> None:
    # def get_pixel_format(self) -> PixelFormat: ...
    # def set_pixel_format(self, value: PixelFormat) -> None: ...
    # def get_gain(self) -> str:
    # def set_gain(self, value: str) -> None:
    # def get_offset(self) -> str:
    # def set_offset(self, value: str) -> None:
    # def get_readout_mode(self) -> str:
    # def set_readout_mode(self, value: str) -> None:
    # def get_readout_time(self) -> str:
    # def set_readout_time(self, value: str) -> None:
    # def get_actual_interval_ms(self) -> str:
    # def set_actual_interval_ms(self, value: str) -> None:
    # def get_interval_ms(self) -> str:
    # def set_interval_ms(self, value: str) -> None:
    # def get_em_gain(self) -> str:
    # def set_em_gain(self, value: str) -> None:
    # def get_ccd_temperature(self) -> str:
    # def set_ccd_temperature(self, value: str) -> None:
    # def get_ccd_temperature_set_point(self) -> str:
    # def set_ccd_temperature_set_point(self, value: str) -> None:

    def __init__(self) -> None:
        super().__init__()
        self._acquisition_thread: None | threading.Thread = None
        self._stop_event = threading.Event()
        self.register_standard_properties()

    def register_standard_properties(self) -> None:
        """Inspect the class for standard properties and register them."""
        cls = type(self)
        for name, (snake_name, prop_type) in self.STANDARD_PROPERTIES.items():
            if getter := getattr(cls, f"get_{snake_name}", None):
                setter = getattr(cls, f"set_{snake_name}", None)
                self.register_property(
                    name=name,
                    property_type=prop_type,
                    getter=getter,
                    setter=setter,
                )

    # Standard Properties, default implementations -------------------

    # We always implement a standard binning getter.  It does not
    # mean that the camera supports binning, unless they implement a setter.
    def get_binning(self) -> int:
        """Get the binning factor for the camera."""
        return 1

    # Threading ------------------------------------------------------

    def start_sequence_thread(
        self,
        n: int,
        get_buffer: Callable[[], np.ndarray],
        notify: Callable[[Mapping], None],
    ) -> None:
        """Acquire a sequence of n images in a background thread."""
        # Stop any existing acquisition
        self._stop_event.set()
        if self._acquisition_thread is not None:
            self._acquisition_thread.join()

        # Reset stop event for new acquisition
        self._stop_event.clear()

        # Start acquisition in background thread
        self._acquisition_thread = threading.Thread(
            target=self.start_sequence, args=(n, get_buffer, notify), daemon=True
        )
        self._acquisition_thread.start()

    def stop_sequence(self) -> None:
        """Stop the current sequence acquisition."""
        self._stop_event.set()
        if self._acquisition_thread is not None:
            self._acquisition_thread.join()
            self._acquisition_thread = None
