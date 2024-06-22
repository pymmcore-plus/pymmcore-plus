from typing import Any, List, Literal, Optional, Tuple, TypedDict

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


class PropertyInfo(TypedDict):
    """Information about a single device property."""

    name: str
    value: Optional[str]
    data_type: Literal["undefined", "float", "int", "str"]
    allowed_values: Optional[Tuple[str, ...]]
    is_read_only: bool
    is_pre_init: bool
    limits: NotRequired[Tuple[float, float]]
    sequenceable: bool
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
    parent_label: Optional[str]  # None on hub devices

    # state device only
    labels: NotRequired[Tuple[str, ...]]
    # focus device only
    focus_direction: NotRequired[Literal["Unknown", "TowardSample", "AwayFromSample"]]
    # hub device only
    child_names: NotRequired[Tuple[str, ...]]


class SystemInfo(TypedDict):
    """General system information."""

    pymmcore_version: str
    pymmcore_plus_version: str
    mmcore_version: str
    device_api_version: str
    device_adapter_search_paths: Tuple[str, ...]
    system_configuration: Optional[str]
    primary_log_file: str
    circular_buffer_memory_footprint: int
    buffer_total_capacity: int
    buffer_free_capacity: int
    timeout_ms: int
    # remaining_image_count: int


class ImageInfo(TypedDict):
    """Information about the current image structure."""

    bytes_per_pixel: int
    current_pixel_size_config: str
    exposure: float
    image_bit_depth: int
    image_buffer_size: int
    image_height: int
    image_width: int
    magnification_factor: float
    number_of_camera_channels: int
    number_of_components: int
    pixel_size_affine: Tuple[float, float, float, float, float, float]
    pixel_size_um: float
    roi: List[int]
    camera_device: str
    multi_roi: NotRequired[Tuple[List[int], List[int], List[int], List[int]]]


class Position(TypedDict):
    """Represents a position in 3D space and focus."""

    x: Optional[float]
    y: Optional[float]
    focus: Optional[float]


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
    pixel_size_affine: Tuple[float, float, float, float, float, float]


class ConfigGroup(TypedDict):
    """A group of configuration presets."""

    name: str
    presets: Tuple[ConfigPreset, ...]


class SummaryMetaV1(TypedDict, total=False):
    """Complete summary metadata for the system. Version 1.0."""

    devices: Tuple[DeviceInfo, ...]
    """A special list."""
    system_info: SystemInfo
    image_info: ImageInfo
    config_groups: Tuple[ConfigGroup, ...]
    pixel_size_configs: Tuple[PixelSizeConfigPreset, ...]
    position: Position
    mda_sequence: NotRequired[useq.MDASequence]
    date_time: str
    format: Literal["summary-dict-full"]
    version: Literal["1.0"]


class FrameMetaV1(TypedDict, total=False):
    """Metadata for a single frame. Version 1.0."""

    exposure_ms: float
    pixel_size_um: float
    position: Position
    camera_device: Optional[str]
    mda_event: NotRequired[useq.MDAEvent]
    runner_time: NotRequired[float]
    property_values: Tuple[PropertyValue, ...]
    format: Literal["frame-dict-minimal"]
    version: Literal["1.0"]
