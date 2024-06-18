from __future__ import annotations

import datetime
from contextlib import suppress
from typing import TYPE_CHECKING, Any, ClassVar, Literal

import msgspec
from msgspec import Struct, field

if TYPE_CHECKING:
    from typing import Self, TypeAlias

    from pymmcore_plus.core import CMMCorePlus


class Format:
    SUMMARY_FULL: Literal["summary"] = "summary"
    FRAME: Literal["frame"] = "frame"


DeviceLabel: TypeAlias = str
PropertyName: TypeAlias = str
PresetName: TypeAlias = str

KW_ONLY = {"kw_only": True}
FROZEN = {"frozen": True}


def _now_isoformat() -> str:
    return datetime.datetime.now().isoformat()


class PyMMCoreStruct(Struct):
    """Convenience methods for structs, following Pydantic API (just in case)."""

    def model_dump(self) -> dict[str, Any]:
        """Convert the struct to a dictionary."""
        return msgspec.to_builtins(self)  # type: ignore

    @classmethod
    def model_validate(cls, obj: Any, *, strict: bool = True) -> Self:
        """Create a struct from a dictionary."""
        return msgspec.convert(obj, cls, strict=strict)

    def model_dump_json(self, *, indent: int | None = None) -> bytes:
        """Convert the struct to a JSON string."""
        data = msgspec.json.encode(self)
        if indent is not None:
            return msgspec.json.format(data, indent=indent)
        return data

    @classmethod
    def model_validate_json(
        cls, json_data: bytes | str, *, strict: bool = True
    ) -> Self:
        """Create struct from JSON bytes or string."""
        return msgspec.json.decode(json_data, type=cls, strict=strict)

    @classmethod
    def model_json_schema(cls) -> dict[str, Any]:
        """Return the JSON schema for the struct."""
        return msgspec.json.schema(cls)


class DeviceInfo(PyMMCoreStruct, **KW_ONLY, **FROZEN):
    """Information about a specific device."""

    type: str
    description: str
    library: str
    name: str
    label: str | None = None

    @classmethod
    def from_core(cls, core: CMMCorePlus, *, label: str, **kwargs: Any) -> Self:
        return cls(
            type=core.getDeviceType(label).name,
            description=core.getDeviceDescription(label),
            library=core.getDeviceLibrary(label),
            name=core.getDeviceName(label),
            label=label,
        )


class SystemInfo(PyMMCoreStruct, **KW_ONLY, **FROZEN):
    """General system information."""

    api_version_info: str
    buffer_free_capacity: int
    buffer_total_capacity: int
    circular_buffer_memory_footprint: int
    device_adapter_search_paths: tuple[str, ...]
    primary_log_file: str
    remaining_image_count: int
    timeout_ms: int
    version_info: str

    @classmethod
    def from_core(cls, core: CMMCorePlus, **kwargs: Any) -> Self:
        return cls(
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


class ImageInfo(PyMMCoreStruct, **KW_ONLY, **FROZEN):
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
    pixel_size_affine: tuple[float, float, float, float, float, float]
    pixel_size_um: float
    roi: list[int]
    camera_device: str
    multi_roi: tuple[list[int], list[int], list[int], list[int]] | None = None

    @classmethod
    def from_core(cls, core: CMMCorePlus, **kwargs: Any) -> Self:
        try:
            multi_roi = core.getMultiROI()
        except RuntimeError:
            multi_roi = None
        return cls(
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


class PositionInfo(PyMMCoreStruct, **KW_ONLY, **FROZEN):
    """Represents a position in 3D space and focus."""

    x: float | None
    y: float | None
    focus: float | None

    @property
    def z(self) -> float | None:
        return self.focus

    @classmethod
    def from_core(cls, core: CMMCorePlus, **kwargs: Any) -> Self:
        x, y, focus = None, None, None
        with suppress(Exception):
            x = core.getXPosition()
            y = core.getYPosition()
        with suppress(Exception):
            focus = core.getPosition()
        return cls(x=x, y=y, focus=focus)


class Setting(PyMMCoreStruct, **KW_ONLY, **FROZEN):
    """A single device property setting in a configuration group."""

    device: str
    property: str
    value: Any


class ConfigGroup(PyMMCoreStruct, **KW_ONLY, **FROZEN):
    """A group of device property settings."""

    settings: tuple[Setting, ...]
    name: str | None = None


class PixelSizeConfig(ConfigGroup, **KW_ONLY, **FROZEN):
    """A configuration group for pixel size settings."""

    pixel_size_um: float
    pixel_size_affine: tuple[float, float, float, float, float, float]

    @classmethod
    def from_core(cls, core: CMMCorePlus, *, config_name: str, **kwargs: Any) -> Self:
        return cls(
            name=config_name,
            settings=tuple(
                Setting(device=dev, property=prop, value=val)
                for dev, prop, val in core.getPixelSizeConfigData(config_name)
            ),
            pixel_size_um=core.getPixelSizeUmByID(config_name),
            pixel_size_affine=core.getPixelSizeAffineByID(config_name),  # type: ignore
        )


class SummaryMetaV1(PyMMCoreStruct, **KW_ONLY, **FROZEN):
    """Summary current state of the system. Version 1."""

    devices: dict[DeviceLabel, DeviceInfo]
    properties: dict[DeviceLabel, dict[PropertyName, Any]]
    system_info: SystemInfo
    image_info: ImageInfo
    pixel_size_configs: dict[PresetName, PixelSizeConfig]
    position: PositionInfo
    time: str = field(default_factory=_now_isoformat)

    format: Literal["summary"] = Format.SUMMARY_FULL
    version: Literal["1.0"] = "1.0"

    @classmethod
    def from_core(cls, core: CMMCorePlus, **kwargs: Any) -> Self:
        return cls(
            devices=_devices_info(core),
            properties=_properties_state(core, cached=kwargs.get("cached", True)),
            system_info=SystemInfo.from_core(core),
            image_info=ImageInfo.from_core(core),
            position=PositionInfo.from_core(core),
            pixel_size_configs=_pixel_size_configs(core),
        )


def _devices_info(core: CMMCorePlus) -> dict[str, DeviceInfo]:
    """Return a dictionary of device information for all loaded devices."""
    return {
        lbl: DeviceInfo.from_core(core, label=lbl) for lbl in core.getLoadedDevices()
    }


def _properties_state(
    core: CMMCorePlus, cached: bool = True, error_value: Any = None
) -> dict[DeviceLabel, dict[PropertyName, Any]]:
    """Return a dictionary of device properties values for all loaded devices."""
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


def _pixel_size_configs(core: CMMCorePlus) -> dict[PresetName, PixelSizeConfig]:
    """Return a dictionary of pixel size configurations."""
    return {
        config_name: PixelSizeConfig.from_core(core, config_name=config_name)
        for config_name in core.getAvailablePixelSizeConfigs()
    }


class FrameMetaV1(PyMMCoreStruct, **KW_ONLY, **FROZEN):
    """Metadata for a frame during an MDA. Version 1.

    This is intentionally minimal to avoid unnecessary overhead.
    """

    exposure_ms: float
    pixel_size_um: float
    position: PositionInfo
    time: str = field(default_factory=_now_isoformat)

    format: Literal["frame"] = Format.FRAME
    version: Literal["1.0"] = "1.0"

    @classmethod
    def from_core(cls, core: CMMCorePlus, **kwargs: Any) -> Self:
        cached = kwargs.get("cached", True)
        return cls(
            exposure_ms=core.getExposure(),
            pixel_size_um=core.getPixelSizeUm(cached),  # true == cached
            position=PositionInfo.from_core(core),
        )
