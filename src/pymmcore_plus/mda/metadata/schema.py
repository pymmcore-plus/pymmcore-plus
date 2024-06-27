from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict

import useq
from typing_extensions import NotRequired

__all__ = [
    "FrameMetaV1",
    "SummaryMetaV1",
    "ConfigGroup",
    "ConfigPreset",
    "DeviceInfo",
    "ImageInfo",
    "PixelSizeConfigPreset",
    "Position",
    "PropertyInfo",
    "PropertyValue",
    "SystemInfo",
]

AffineTuple = Tuple[float, float, float, float, float, float]


class PropertyInfo(TypedDict):
    """Information about a single device property."""

    name: str
    value: Optional[str]
    data_type: Literal["undefined", "float", "int", "str"]
    is_read_only: bool
    allowed_values: NotRequired[Tuple[str, ...]]
    is_pre_init: NotRequired[bool]
    limits: NotRequired[Tuple[float, float]]
    sequenceable: NotRequired[bool]
    sequence_max_length: NotRequired[int]
    # device_label: str


class DeviceInfo(TypedDict):
    """Information about a specific device."""

    label: str
    library: str
    name: str
    type: str
    description: str
    properties: Tuple[PropertyInfo, ...]
    # hub devices and non-peripheral devices will have no parent_label
    parent_label: NotRequired[str]

    # state device only
    labels: NotRequired[Tuple[str, ...]]
    # hub device only
    child_names: NotRequired[Tuple[str, ...]]
    # stage/focus device only
    is_continuous_focus_drive: NotRequired[bool]
    focus_direction: NotRequired[Literal["Unknown", "TowardSample", "AwayFromSample"]]
    # camera, slm, stage/focus, or XYStage devices only
    is_sequenceable: NotRequired[bool]


class SystemInfo(TypedDict):
    """General system information."""

    pymmcore_version: str
    pymmcore_plus_version: str
    mmcore_version: str
    device_api_version: str
    device_adapter_search_paths: Tuple[str, ...]
    system_configuration_file: Optional[str]
    primary_log_file: str
    sequence_buffer_size_mb: int  # core returns this as MB
    continuous_focus_enabled: bool
    continuous_focus_locked: bool
    auto_shutter: bool
    timeout_ms: NotRequired[int]


class ImageInfo(TypedDict):
    """Information about the current image structure."""

    # Label of the loaded camera device
    camera_label: str

    # The shape (height, width[, num_components]) of the numpy array
    # that will be returned for each snap of the camera
    # this will be length 2 (if components_per_pixel is 1) or 3 otherwise
    #
    plane_shape: Tuple[int, ...]
    # number of pixels in the image  (should we have both this and plane shape?)
    image_height: int
    image_width: int

    # The numpy dtype of the image array (uint8, uint16, etc...)
    dtype: str

    # bytes per pixel is the total number of bytes per pixel, in the image buffer.
    # This including all components so RGB32 is 4 bytes per pixel
    # and a 12-bit camera with a 16-bit buffer would be 2 bytes per pixel
    bytes_per_pixel: int

    # Number of components per pixel, RGBA is 4, GRAY is 1, etc...
    # I think this will always be either 4 or 1
    # note also that CMMCorePlus will fix BGRA to RGB, so the numpy array returned
    # will have shape(..., 3) even though MMCore says components_per_pixel is 4
    components_per_pixel: int  # rgb or not

    # component_bit_depth is the "true" bit depth of the image, irrespective of the
    # buffer size.  So a 12-bit gray camera will have 12 bits per component, and
    # 1 components_per_pixel... even though the final numpy array will have
    # dtype uint16 and bytes_per_pixel will be 2.
    # An RGBA32 camera would have 8 bits per component and 4 components_per_pixel
    component_bit_depth: int

    # format of the pixel data, like "RGB32", "GRAY16", etc...
    pixel_format: Literal["GRAY8", "GRAY16", "GRAY32", "RGB32", "RGB64", ""]

    # name of the currently active pixel size configuration
    pixel_size_config_name: str

    # the product of magnification of all loaded devices of type MagnifierDevice
    # If no devices are found, or all have magnification=1, this will not be present
    magnification_factor: NotRequired[float]

    # this will be != 1 for things like multi-camera device,
    # or any "single" device adapter that manages multiple detectors, like PMTs, etc...
    num_camera_adapter_channels: NotRequired[int]

    pixel_size_um: float
    # will not be present if equal to the default of (1,0,0,0,1,0)
    pixel_size_affine: NotRequired[AffineTuple]

    # will not be present if the ROI is the full image
    roi: NotRequired[Tuple[int, int, int, int]]
    # will not be present if camera devices not support multiple ROIs, or if multiple
    # ROIs are not currently being used
    multi_roi: NotRequired[Tuple[List[int], List[int], List[int], List[int]]]


class Position(TypedDict):
    """Represents a position in 3D space and focus."""

    x: Optional[float]
    y: Optional[float]
    z: Optional[float]


class PropertyValue(TypedDict):
    """A single device property setting in a configuration group."""

    dev: str
    prop: str
    val: Any


class ConfigPreset(TypedDict):
    """A group of device property settings."""

    name: str
    settings: Tuple[PropertyValue, ...]


class PixelSizeConfigPreset(ConfigPreset):
    """A specialized group of device property settings for a pixel size preset."""

    pixel_size_um: float
    pixel_size_affine: NotRequired[AffineTuple]


class ConfigGroup(TypedDict):
    """A group of configuration presets."""

    name: str
    presets: Tuple[ConfigPreset, ...]


class SummaryMetaV1(TypedDict, total=False):
    """Complete summary metadata for the system. Version 1.0."""

    devices: Tuple[DeviceInfo, ...]
    system_info: SystemInfo
    image_infos: Tuple[ImageInfo, ...]
    config_groups: Tuple[ConfigGroup, ...]
    pixel_size_configs: Tuple[PixelSizeConfigPreset, ...]
    position: Position
    mda_sequence: NotRequired[useq.MDASequence]
    datetime: str
    format: Literal["summary-dict-full"]
    version: Literal["1.0"]
    extra: NotRequired[Dict[str, Any]]


class FrameMetaV1(TypedDict, total=False):
    """Metadata for a single frame. Version 1.0."""

    # image_info: ImageInfo
    pixel_size_um: float
    camera_device: Optional[str]

    exposure_ms: float
    position: Position
    property_values: Tuple[PropertyValue, ...]
    mda_event: NotRequired[useq.MDAEvent]
    runner_time_ms: NotRequired[float]
    hardware_triggered: NotRequired[bool]
    images_remaining_in_buffer: NotRequired[int]
    format: Literal["frame-dict-minimal"]
    version: Literal["1.0"]
    extra: NotRequired[Dict[str, Any]]
    camera_metadata: NotRequired[Dict[str, Any]]
