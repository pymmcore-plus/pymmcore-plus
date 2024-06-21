from __future__ import annotations

import datetime
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Literal, TypedDict

import useq  # noqa: TCH002

from pymmcore_plus.core._constants import Keyword, PymmcPlusConstants

from ._base import MetadataProvider

if TYPE_CHECKING:
    from typing import TypeAlias

    from pymmcore_plus.core import CMMCorePlus

__all__ = ["FrameMetaDictV1", "SummaryMetaDictV1"]


DeviceLabel: TypeAlias = str
PropertyName: TypeAlias = str
PresetName: TypeAlias = str

KW_ONLY = {"kw_only": True}
FROZEN = {"frozen": True}


def _now_isoformat() -> str:
    return datetime.datetime.now().isoformat()


# def _enc_hook(obj: Any) -> Any:
#     """Custom encoder for msgspec."""
#     pydantic = sys.modules.get("pydantic")
#     if pydantic and isinstance(obj, pydantic.BaseModel):
#         try:
#             return obj.model_dump(mode="json")
#         except AttributeError:
#             return obj.dict()

#     # Raise a NotImplementedError for other types
#     raise NotImplementedError(f"Objects of type {type(obj)!r} are not supported")


# def _dec_hook(type: type, obj: Any) -> Any:
#     """Custom decoder for msgspec."""
#     # `type` here is the value of the custom type annotation being decoded.
#     if TYPE_CHECKING:
#         import pydantic
#     else:
#         pydantic = sys.modules.get("pydantic")
#     if pydantic and issubclass(type, pydantic.BaseModel):
#         try:
#             return type.model_validate(obj)
#         except AttributeError:
#             return type.parse_obj(obj)

#     # Raise a NotImplementedError for other types
#     raise NotImplementedError(f"Objects of type {type!r} are not supported")


# def model_dump(obj) -> dict[str, Any]:
#     """Convert the struct to a dictionary."""
#     return msgspec.to_builtins(obj, enc_hook=_enc_hook)  # type: ignore

# @classmethod
# def model_validate(cls, obj: Any, *, strict: bool = True) -> Self:
#     """Create a struct from a dictionary."""
#     return msgspec.convert(obj, type=cls, strict=strict, dec_hook=_dec_hook)

# def model_dump_json(self, *, indent: int | None = None) -> bytes:
#     """Convert the struct to a JSON string."""
#     data = msgspec.json.encode(self, enc_hook=_enc_hook)
#     if indent is not None:
#         return msgspec.json.format(data, indent=indent)
#     return data

# @classmethod
# def model_validate_json(
#     cls, json_data: bytes | str, *, strict: bool = True
# ) -> Self:
#     """Create struct from JSON bytes or string."""
#     return msgspec.json.decode(
#         json_data, type=cls, strict=strict, dec_hook=_dec_hook
#     )

# @classmethod
# def model_json_schema(cls) -> dict[str, Any]:
#     """Return the JSON schema for the struct."""
#     return msgspec.json.schema(cls)


class DeviceInfoDict(TypedDict):
    """Information about a specific device."""

    type: str
    description: str
    library: str
    name: str
    label: str | None


def device_info(core: CMMCorePlus, *, label: str) -> DeviceInfoDict:
    return {
        "type": core.getDeviceType(label).name,
        "description": core.getDeviceDescription(label),
        "library": core.getDeviceLibrary(label),
        "name": core.getDeviceName(label),
        "label": label,
    }


class SystemInfoDict(TypedDict):
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


def system_info(core: CMMCorePlus) -> SystemInfoDict:
    return {
        "api_version_info": core.getAPIVersionInfo(),
        "buffer_free_capacity": core.getBufferFreeCapacity(),
        "buffer_total_capacity": core.getBufferTotalCapacity(),
        "circular_buffer_memory_footprint": core.getCircularBufferMemoryFootprint(),
        "device_adapter_search_paths": core.getDeviceAdapterSearchPaths(),
        "primary_log_file": core.getPrimaryLogFile(),
        "remaining_image_count": core.getRemainingImageCount(),
        "timeout_ms": core.getTimeoutMs(),
        "version_info": core.getVersionInfo(),
    }


class ImageInfoDict(TypedDict):
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
    multi_roi: tuple[list[int], list[int], list[int], list[int]] | None


def image_info(core: CMMCorePlus) -> ImageInfoDict:
    try:
        multi_roi = core.getMultiROI()
    except RuntimeError:
        multi_roi = None
    return {
        "bytes_per_pixel": core.getBytesPerPixel(),
        "current_pixel_size_config": core.getCurrentPixelSizeConfig(),
        "exposure": core.getExposure(),
        "image_bit_depth": core.getImageBitDepth(),
        "image_buffer_size": core.getImageBufferSize(),
        "image_height": core.getImageHeight(),
        "image_width": core.getImageWidth(),
        "magnification_factor": core.getMagnificationFactor(),
        "number_of_camera_channels": core.getNumberOfCameraChannels(),
        "number_of_components": core.getNumberOfComponents(),
        "pixel_size_affine": core.getPixelSizeAffine(True),  # type: ignore
        "pixel_size_um": core.getPixelSizeUm(True),
        "roi": core.getROI(),
        "camera_device": core.getCameraDevice(),
        "multi_roi": multi_roi,
    }


class PositionInfoDict(TypedDict):
    """Represents a position in 3D space and focus."""

    x: float | None
    y: float | None
    focus: float | None


def position_info(core: CMMCorePlus) -> PositionInfoDict:
    x, y, focus = None, None, None
    with suppress(Exception):
        x = core.getXPosition()
        y = core.getYPosition()
    with suppress(Exception):
        focus = core.getPosition()
    return {"x": x, "y": y, "focus": focus}


class SettingDict(TypedDict):
    """A single device property setting in a configuration group."""

    device: str
    property: str
    value: Any


class ConfigGroupDict(TypedDict):
    """A group of device property settings."""

    settings: tuple[SettingDict, ...]
    name: str | None


class PixelSizeConfigDict(ConfigGroupDict):
    """A configuration group for pixel size settings."""

    pixel_size_um: float
    pixel_size_affine: tuple[float, float, float, float, float, float]


def pixel_size_config(core: CMMCorePlus, *, config_name: str) -> PixelSizeConfigDict:
    return {
        "name": config_name,
        "settings": tuple(
            {"device": dev, "property": prop, "value": val}
            for dev, prop, val in core.getPixelSizeConfigData(config_name)
        ),
        "pixel_size_um": core.getPixelSizeUmByID(config_name),
        "pixel_size_affine": core.getPixelSizeAffineByID(config_name),  # type: ignore
    }


class SummaryMetaDictV1Dict(TypedDict):
    devices: dict[DeviceLabel, DeviceInfoDict]
    properties: dict[DeviceLabel, dict[PropertyName, Any]]
    system_info: SystemInfoDict
    image_info: ImageInfoDict
    pixel_size_configs: dict[PresetName, PixelSizeConfigDict]
    position: PositionInfoDict
    mda_sequence: useq.MDASequence | None
    date_time: str
    format: Literal["summary-struct-full"]
    version: Literal["1.0"]


class SummaryMetaDictV1(MetadataProvider):
    """Summary current state of the system. Version 1."""

    @classmethod
    def from_core(
        cls, core: CMMCorePlus, extra: dict[str, Any]
    ) -> SummaryMetaDictV1Dict:
        return {
            "devices": _devices_info(core),
            "properties": _properties_state(core, cached=extra.get("cached", True)),
            "system_info": system_info(core),
            "image_info": image_info(core),
            "position": position_info(core),
            "pixel_size_configs": _pixel_size_configs(core),
            "mda_sequence": extra.get(PymmcPlusConstants.MDA_SEQUENCE.value),
            "format": "summary-struct-full",
            "date_time": _now_isoformat(),
            "version": "1.0",
        }

    @classmethod
    def provider_key(cls) -> str:
        return "summary-struct-full"

    @classmethod
    def provider_version(cls) -> str:
        return "1.0"

    @classmethod
    def metadata_type(cls) -> Literal["summary"]:
        return "summary"


def _devices_info(core: CMMCorePlus) -> dict[str, DeviceInfoDict]:
    """Return a dictionary of device information for all loaded devices."""
    return {lbl: device_info(core, label=lbl) for lbl in core.getLoadedDevices()}


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


def _pixel_size_configs(core: CMMCorePlus) -> dict[PresetName, PixelSizeConfigDict]:
    """Return a dictionary of pixel size configurations."""
    return {
        config_name: pixel_size_config(core, config_name=config_name)
        for config_name in core.getAvailablePixelSizeConfigs()
    }


class FrameMetaDictV1Dict(TypedDict):
    exposure_ms: float
    pixel_size_um: float
    position: PositionInfoDict
    mda_event: useq.MDAEvent | None
    runner_time: float | None
    camera_device: str | None
    config_state: dict[str, dict[str, Any]] | None
    format: Literal["frame-dict-minimal"]
    version: Literal["1.0"]


class FrameMetaDictV1(MetadataProvider):
    """Metadata for a frame during an MDA. Version 1.

    This is intentionally minimal to avoid unnecessary overhead.
    """

    @classmethod
    def from_core(cls, core: CMMCorePlus, extra: dict[str, Any]) -> FrameMetaDictV1Dict:
        if mda_event := extra.get(PymmcPlusConstants.MDA_EVENT.value):
            run_time = mda_event.metadata.get(PymmcPlusConstants.RUNNER_TIME_SEC.value)
        else:
            run_time = None
        return {
            "exposure_ms": core.getExposure(),
            "pixel_size_um": core.getPixelSizeUm(extra.get("cached", True)),
            "position": position_info(core),
            "mda_event": mda_event,
            "runner_time": run_time,
            "camera_device": extra.get(Keyword.CoreCamera.value),
            "config_state": extra.get(PymmcPlusConstants.CONFIG_STATE.value),
            "format": "frame-dict-minimal",
            "version": "1.0",
        }

    @classmethod
    def provider_key(cls) -> str:
        return "frame-struct-minimal"

    @classmethod
    def provider_version(cls) -> str:
        return "1.0"

    @classmethod
    def metadata_type(cls) -> Literal["frame"]:
        return "frame"
