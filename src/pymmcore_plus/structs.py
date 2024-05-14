from __future__ import annotations

import datetime
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Self

import msgspec
from msgspec import Struct, field

if TYPE_CHECKING:
    from pymmcore_plus.core import CMMCorePlus

KW_ONLY = {"kw_only": True}
FROZEN = {"frozen": True}


class PyMMCoreStruct(Struct):
    def to_dict(self) -> dict[str, Any]:
        """Convert the struct to a dictionary."""
        return msgspec.to_builtins(self)  # type: ignore

    @classmethod
    def from_dict(cls, d: object, *, strict: bool = True) -> Self:
        """Create a struct from a dictionary."""
        return msgspec.convert(d, cls, strict=strict)

    def to_json(self, *, indent: int | None = None) -> bytes:
        """Convert the struct to a JSON string."""
        data = msgspec.json.encode(self)
        if indent is not None:
            return msgspec.json.format(data, indent=indent)
        return data

    @classmethod
    def from_json(cls, buf: bytes | str, *, strict: bool = True) -> Self:
        """Create struct from JSON bytes or string."""
        return msgspec.json.decode(buf, type=cls, strict=strict)


class DeviceInfo(PyMMCoreStruct, **KW_ONLY, **FROZEN):
    type: str
    description: str
    library: str
    name: str
    label: str | None = None


class SystemInfo(PyMMCoreStruct, **KW_ONLY, **FROZEN):
    api_version_info: str
    buffer_free_capacity: int
    buffer_total_capacity: int
    circular_buffer_memory_footprint: int
    device_adapter_search_paths: tuple[str, ...]
    primary_log_file: str
    remaining_image_count: int
    timeout_ms: int
    version_info: str


class ImageInfo(PyMMCoreStruct, **KW_ONLY, **FROZEN):
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
    pixel_size_affine: tuple[float, float, float, float, float, float]
    pixel_size_um: float
    roi: list[int]
    camera_device: str
    multi_roi: tuple[list[int], list[int], list[int], list[int]] | None = None


class PositionInfo(PyMMCoreStruct, **KW_ONLY, **FROZEN):
    x: float | None
    y: float | None
    focus: float | None


class SummaryMetaV1(PyMMCoreStruct, **KW_ONLY, **FROZEN):
    version: str = "1.0"
    time: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    devices: dict[str, DeviceInfo]
    properties: dict[str, dict[str, Any]]
    system_info: SystemInfo
    image_info: ImageInfo | None = None
    pixel_size_configs: dict[str, PixelSizeConfig] | None = None
    position: PositionInfo | None = None


def summary_metadata_full_v1(core: CMMCorePlus, cached: bool = True) -> SummaryMetaV1:
    return SummaryMetaV1(
        devices=devices_info(core),
        properties=properties_state(core, cached=cached),
        system_info=system_info(core),
        image_info=image_info(core),
        position=position_info(core),
        pixel_size_configs=pixel_size_configs(core),
    )


class Setting(PyMMCoreStruct, **KW_ONLY, **FROZEN):
    device: str
    property: str
    value: Any


class ConfigGroup(PyMMCoreStruct, **KW_ONLY, **FROZEN):
    settings: tuple[Setting, ...]
    name: str | None = None


class PixelSizeConfig(ConfigGroup, **KW_ONLY, **FROZEN):
    pixel_size_um: float
    pixel_size_affine: tuple[float, float, float, float, float, float]


def pixel_size_config(core: CMMCorePlus, config_name: str) -> PixelSizeConfig:
    return PixelSizeConfig(
        name=config_name,
        settings=tuple(
            Setting(device=dev, property=prop, value=val)
            for dev, prop, val in core.getPixelSizeConfigData(config_name)
        ),
        pixel_size_um=core.getPixelSizeUmByID(config_name),
        pixel_size_affine=core.getPixelSizeAffineByID(config_name),  # type: ignore
    )


def pixel_size_configs(core: CMMCorePlus) -> dict[str, PixelSizeConfig]:
    return {
        name: pixel_size_config(core, name)
        for name in core.getAvailablePixelSizeConfigs()
    }


def device_info(core: CMMCorePlus, label: str) -> DeviceInfo:
    return DeviceInfo(
        type=core.getDeviceType(label).name,
        description=core.getDeviceDescription(label),
        library=core.getDeviceLibrary(label),
        name=core.getDeviceName(label),
        label=label,
    )


def devices_info(core: CMMCorePlus) -> dict[str, DeviceInfo]:
    return {label: device_info(core, label) for label in core.getLoadedDevices()}


def properties_state(
    core: CMMCorePlus, cached: bool = True, error_value: Any = None
) -> dict[str, dict[str, Any]]:
    # this actually appears to be faster than getSystemStateCache
    getProp = core.getPropertyFromCache if cached else core.getProperty
    device_state: dict = {}
    for dev in core.getLoadedDevices():
        dd = device_state.setdefault(dev, {})
        for prop in core.getDevicePropertyNames(dev):
            try:
                val = getProp(dev, prop)
            except Exception:
                val = error_value
            dd[prop] = val
    return device_state


def system_info(core: CMMCorePlus) -> SystemInfo:
    return SystemInfo(
        api_version_info=core.getAPIVersionInfo(),
        buffer_free_capacity=core.getBufferFreeCapacity(),
        buffer_total_capacity=core.getBufferTotalCapacity(),
        circular_buffer_memory_footprint=core.getCircularBufferMemoryFootprint(),
        device_adapter_search_paths=core.getDeviceAdapterSearchPaths(),
        primary_log_file=core.getPrimaryLogFile(),
        remaining_image_count=core.getRemainingImageCount(),
        timeout_ms=core.getTimeoutMs(),
        version_info=core.getVersionInfo(),
    )


def position_info(core: CMMCorePlus) -> PositionInfo:
    x, y, focus = None, None, None
    with suppress(Exception):
        x = core.getXPosition()
        y = core.getYPosition()
    with suppress(Exception):
        focus = core.getPosition()
    return PositionInfo(x=x, y=y, focus=focus)


def image_info(core: CMMCorePlus) -> ImageInfo:
    try:
        multi_roi = core.getMultiROI()
    except RuntimeError:
        multi_roi = None
    return ImageInfo(
        bytes_per_pixel=core.getBytesPerPixel(),
        current_pixel_size_config=core.getCurrentPixelSizeConfig(),
        exposure=core.getExposure(),
        image_bit_depth=core.getImageBitDepth(),
        image_buffer_size=core.getImageBufferSize(),
        image_height=core.getImageHeight(),
        image_width=core.getImageWidth(),
        magnification_factor=core.getMagnificationFactor(),
        number_of_camera_channels=core.getNumberOfCameraChannels(),
        number_of_components=core.getNumberOfComponents(),
        pixel_size_affine=core.getPixelSizeAffine(True),  # type: ignore
        pixel_size_um=core.getPixelSizeUm(True),  # type: ignore
        roi=core.getROI(),
        camera_device=core.getCameraDevice(),
        multi_roi=multi_roi,
    )
