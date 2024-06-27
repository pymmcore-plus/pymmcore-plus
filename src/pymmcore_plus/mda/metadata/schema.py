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

    bytes_per_pixel: int
    current_pixel_size_config: str
    exposure: float
    # image_buffer_size: int
    # image_height: int
    # image_width: int
    magnification_factor: float
    # this will be != 1 for things like multi-camera device,
    # or any "single" device adapter that manages multiple detectors, like PMTs, etc...
    number_of_camera_adapter_channels: NotRequired[int]
    components_per_pixel: int  # rgb or not
    component_bit_depth: int
    # some way to suggest the image format, like RGB, etc...

    pixel_size_affine: NotRequired[AffineTuple]
    pixel_size_um: float
    roi: List[int]
    camera_device: str
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
    image_info: ImageInfo
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
    runner_time: NotRequired[float]
    in_sequence: NotRequired[bool]
    remaining_image_count: NotRequired[int]
    format: Literal["frame-dict-minimal"]
    version: Literal["1.0"]
    extra: NotRequired[Dict[str, Any]]
    camera_metadata: NotRequired[Dict[str, Any]]
