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
    # stage or XYstage device only
    is_stage_sequenceable: NotRequired[bool]
    # stage device only
    is_continuous_focus_drive: NotRequired[bool]
    # is_stage_linear_sequenceable: NotRequired[bool]
    # camera device only
    is_exposure_sequenceable: NotRequired[bool]


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
    timeout_ms: int
    # remaining_image_count: int
    continuous_focus_enabled: bool
    continuous_focus_locked: bool
    auto_shutter: bool


class ImageInfo(TypedDict):
    """Information about the current image structure."""

    label: str  # some concept of camera device, magnification

    bytes_per_pixel: int
    current_pixel_size_config: str
    exposure: float
    # image_buffer_size: int
    # image_height: int
    # image_width: int
    magnification_factor: float
    number_of_camera_channels: int
    number_of_components: int  # rgb or not
    component_bit_depth: int
    # some way to suggest the image format, like RGB, etc...

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
    system_info: SystemInfo
    image_info: tuple[ImageInfo, ...]
    config_groups: Tuple[ConfigGroup, ...]
    pixel_size_configs: Tuple[PixelSizeConfigPreset, ...]
    position: Position
    mda_sequence: NotRequired[useq.MDASequence]
    date_time: str
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
    mda_event: NotRequired[useq.MDAEvent]
    runner_time: NotRequired[float]
    property_values: Tuple[PropertyValue, ...]
    in_sequence_acquisition: NotRequired[bool]
    remaining_image_count: NotRequired[int]
    format: Literal["frame-dict-minimal"]
    version: Literal["1.0"]
    extra: NotRequired[Dict[str, Any]]
