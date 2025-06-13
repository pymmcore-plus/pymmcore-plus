from __future__ import annotations

from abc import abstractmethod
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, ClassVar, Literal

from pymmcore_plus.core._constants import DeviceType, Keyword, PixelFormat

from ._device_base import Device

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    import numpy as np
    from numpy.typing import DTypeLike


class CameraDevice(Device):
    # mandatory methods for Camera device adapters

    _TYPE: ClassVar[Literal[DeviceType.Camera]] = DeviceType.Camera

    @abstractmethod
    def get_exposure(self) -> float:
        """Get the current exposure time in milliseconds."""
        ...

    @abstractmethod
    def set_exposure(self, exposure: float) -> None:
        """Set the exposure time in milliseconds."""
        ...

    @abstractmethod
    def shape(self) -> tuple[int, ...]:
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
        n: int | None,
        get_buffer: Callable[[Sequence[int], DTypeLike], np.ndarray],
    ) -> Iterator[Mapping]:
        """Start a sequence acquisition.

        This method should be implemented by the camera device adapter and should
        yield metadata for each acquired image. The implementation should call
        get_buffer() to get a buffer, fill it with image data, then yield the
        metadata for that image.

        The core will handle threading and synchronization.  This function may block.

        Parameters
        ----------
        n : int | None
            If an integer, this is the number of images to acquire.
            If None, the camera should acquire images indefinitely until stopped.
        get_buffer : Callable[[Sequence[int], DTypeLike], np.ndarray]
            A callable that returns a buffer for the camera to fill with image data.
            You should call this with the shape of the image and the dtype
            of the image data.  The core will produce a buffer of the requested shape
            and dtype, and you should fill it (in place) with the image data.

        Yields
        ------
        Mapping
            Metadata for each acquired image. This should be yielded after the
            corresponding buffer has been filled with image data.
        """
        # EXAMPLE USAGE:
        # shape, dtype = self.shape(), self.dtype()
        # if n is None:  # acquire indefinitely until stopped
        #    while True:
        #        yield ...
        #    return
        # for _ in range(n):
        #     image = get_buffer(shape, dtype)
        #     get the image from the camera, and fill the buffer in place
        #     image[:] = <your_camera_data>
        #     notify the core that the buffer is ready, and provide any metadata
        #     yield {"key": "value", ...}  # metadata for the image

        #     TODO:
        #     Open question: who is responsible for key pieces of metadata?
        #     in CMMCore, each of the camera device adapters is responsible for
        #     injecting to following bits of metadata:
        #     - MM::g_Keyword_Metadata_CameraLabel
        #     - MM::g_Keyword_Elapsed_Time_ms (GetCurrentMMTime - start_time)
        #     - MM::g_Keyword_Metadata_ROI_X
        #     - MM::g_Keyword_Metadata_ROI_Y
        #     - MM::g_Keyword_Binning
        #     --- while the CircularBuffer InsertMultiChannel is responsible for adding:
        #     - MM::g_Keyword_Metadata_ImageNumber
        #     - MM::g_Keyword_Elapsed_Time_ms
        #     - MM::g_Keyword_Metadata_TimeInCore
        #     - MM::g_Keyword_Metadata_Width
        #     - MM::g_Keyword_Metadata_Height
        #     - MM::g_Keyword_PixelType

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
            Keyword.Metadata_ROI_X: ("roi_x", int),
            Keyword.Metadata_ROI_Y: ("roi_y", int),
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
        self.register_standard_properties()

    def register_standard_properties(self) -> None:
        """Inspect the class for standard properties and register them."""
        cls = type(self)
        for name, (snake_name, prop_type) in self.STANDARD_PROPERTIES.items():
            if getter := getattr(cls, f"get_{snake_name}", None):
                setter = getattr(cls, f"set_{snake_name}", None)
                seq_loader = getattr(cls, f"load_{snake_name}_sequence", None)
                seq_starter = getattr(cls, f"start_{snake_name}_sequence", None)
                seq_stopper = getattr(cls, f"stop_{snake_name}_sequence", None)
                self.register_property(
                    name=name,
                    property_type=prop_type,
                    getter=getter,
                    setter=setter,
                    sequence_loader=seq_loader,
                    sequence_starter=seq_starter,
                    sequence_stopper=seq_stopper,
                )

    # Standard Properties, default implementations -------------------

    # We always implement a standard binning getter.  It does not
    # mean that the camera supports binning, unless they implement a setter.
    def get_binning(self) -> int:
        """Get the binning factor for the camera."""
        return 1  # pragma: no cover
