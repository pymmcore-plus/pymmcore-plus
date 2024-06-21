from __future__ import annotations

import datetime
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Literal, TypedDict

import useq  # noqa: TCH002

import pymmcore_plus
from pymmcore_plus.core._constants import Keyword, PymmcPlusConstants

from ._base import MetadataProvider

if TYPE_CHECKING:
    from typing import TypeAlias

    from pymmcore_plus.core import CMMCorePlus

__all__ = ["FrameMetaDictV1", "SummaryMetaDictV1"]


DeviceLabel: TypeAlias = str
PropertyName: TypeAlias = str
PresetName: TypeAlias = str


def _now_isoformat() -> str:
    return datetime.datetime.now().isoformat()


class _DeviceInfoDict(TypedDict):
    """Information about a specific device."""

    description: str
    library: str
    name: str
    label: str | None
    parent_label: str | None
    properties: dict[PropertyName, Any]


class StateDeviceInfoDict(_DeviceInfoDict):
    type: Literal["StateDevice"]
    labels: tuple[str, ...]


class StageDeviceInfoDict(_DeviceInfoDict):
    type: Literal["StageDevice"]
    focus_direction: Literal["Unknown", "TowardSample", "AwayFromSample"]


class HubDeviceInfoDict(_DeviceInfoDict):
    type: Literal["HubDevice"]
    child_names: tuple[str, ...] | None


class GenericDeviceInfoDict(_DeviceInfoDict):
    type: str


DeviceInfoDict = (
    GenericDeviceInfoDict
    | StateDeviceInfoDict
    | StageDeviceInfoDict
    | HubDeviceInfoDict
)


def device_info(
    core: CMMCorePlus, *, label: str, cached: bool = True
) -> DeviceInfoDict:
    info = {
        "type": core.getDeviceType(label).name,
        "description": core.getDeviceDescription(label),
        "library": core.getDeviceLibrary(label),
        "name": core.getDeviceName(label),
        "label": label,
        "parent_label": core.getParentLabel(label) or None,
        "properties": properties(core, device=label, cached=cached),
    }
    with suppress(RuntimeError):
        info["child_names"] = core.getInstalledDevices(label)  # type: ignore[assignment]
    return info  # type: ignore[return-value]


class SystemInfoDict(TypedDict):
    """General system information."""

    pymmcore_version: str
    pymmcore_plus_version: str
    api_version_info: str
    buffer_free_capacity: int
    buffer_total_capacity: int
    circular_buffer_memory_footprint: int
    device_adapter_search_paths: tuple[str, ...]
    primary_log_file: str
    # remaining_image_count: int
    timeout_ms: int
    version_info: str
    system_configuration: str | None


def system_info(core: CMMCorePlus) -> SystemInfoDict:
    return {
        "pymmcore_version": pymmcore_plus.__version__,
        "pymmcore_plus_version": pymmcore_plus.__version__,
        "api_version_info": core.getAPIVersionInfo(),
        "buffer_free_capacity": core.getBufferFreeCapacity(),
        "buffer_total_capacity": core.getBufferTotalCapacity(),
        "circular_buffer_memory_footprint": core.getCircularBufferMemoryFootprint(),
        "device_adapter_search_paths": core.getDeviceAdapterSearchPaths(),
        "primary_log_file": core.getPrimaryLogFile(),
        # "remaining_image_count": core.getRemainingImageCount(),
        "timeout_ms": core.getTimeoutMs(),
        "version_info": core.getVersionInfo(),
        "system_configuration": core.systemConfigurationFile(),
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


def position(core: CMMCorePlus) -> PositionInfoDict:
    x, y, focus = None, None, None
    with suppress(Exception):
        x = core.getXPosition()
        y = core.getYPosition()
    with suppress(Exception):
        focus = core.getPosition()
    return {"x": x, "y": y, "focus": focus}


class SettingDict(TypedDict):
    """A single device property setting in a configuration group."""

    dev: str
    prop: str
    val: Any


class ConfigGroupDict(TypedDict):
    """A group of device property settings."""

    settings: list[SettingDict]


def config_group(
    core: CMMCorePlus, *, group_name: str
) -> dict[PresetName, ConfigGroupDict]:
    return {
        preset_name: {
            "settings": [
                SettingDict({"dev": dev, "prop": prop, "val": val})
                for dev, prop, val in core.getConfigData(group_name, preset_name)
            ]
        }
        for preset_name in core.getAvailableConfigs(group_name)
    }


def config_groups(core: CMMCorePlus) -> dict[str, dict[PresetName, ConfigGroupDict]]:
    return {
        group_name: config_group(core, group_name=group_name)
        for group_name in core.getAvailableConfigGroups()
    }


class PixelSizeConfigDict(ConfigGroupDict):
    """A configuration group for pixel size settings."""

    pixel_size_um: float
    pixel_size_affine: tuple[float, float, float, float, float, float]


def pixel_size_config(core: CMMCorePlus, *, config_name: str) -> PixelSizeConfigDict:
    return {
        "pixel_size_um": core.getPixelSizeUmByID(config_name),
        "pixel_size_affine": core.getPixelSizeAffineByID(config_name),  # type: ignore
        "settings": [
            {"dev": dev, "prop": prop, "val": val}
            for dev, prop, val in core.getPixelSizeConfigData(config_name)
        ],
    }


class SummaryMetaDictV1Dict(TypedDict, total=False):
    devices: dict[DeviceLabel, DeviceInfoDict]
    system_info: SystemInfoDict
    image_info: ImageInfoDict
    config_groups: dict[str, dict[PresetName, ConfigGroupDict]]
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
            "devices": devices_info(core, cached=extra.get("cached", True)),
            "system_info": system_info(core),
            "image_info": image_info(core),
            "position": position(core),
            "config_groups": config_groups(core),
            "pixel_size_configs": pixel_size_configs(core),
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


def devices_info(core: CMMCorePlus, cached: bool = True) -> dict[str, DeviceInfoDict]:
    """Return a dictionary of device information for all loaded devices."""
    return {
        lbl: device_info(core, label=lbl, cached=cached)
        for lbl in core.getLoadedDevices()
    }


class PropertyInfoDict(TypedDict):
    """Information about a device property."""

    value: str | None
    data_type: Literal["undefined", "float", "int", "str"]
    allowed_values: tuple[str, ...] | None
    limits: tuple[float, float] | None
    is_read_only: bool

    # is_pre_init: bool
    # device_label: str
    # name: str


def property_info(
    core: CMMCorePlus,
    device: str,
    prop: str,
    *,
    cached: bool = True,
    error_value: Any = None,
) -> PropertyInfoDict:
    """Return a dictionary of device property information."""
    if core.hasPropertyLimits(device, prop):
        limits = (
            core.getPropertyLowerLimit(device, prop),
            core.getPropertyUpperLimit(device, prop),
        )
    else:
        limits = None
    try:
        if cached:
            value = core.getPropertyFromCache(device, prop)
        else:
            value = core.getProperty(device, prop)
    except Exception:
        value = error_value
    return {
        "value": value,
        "data_type": core.getPropertyType(device, prop).__repr__(),
        "allowed_values": core.getAllowedPropertyValues(device, prop),
        "limits": limits,
        "is_read_only": core.isPropertyReadOnly(device, prop),
    }


def properties(
    core: CMMCorePlus, device: str, cached: bool = True, error_value: Any = None
) -> dict[PropertyName, PropertyInfoDict]:
    """Return a dictionary of device properties values for all loaded devices."""
    # this actually appears to be faster than getSystemStateCache
    return {
        prop: property_info(core, device, prop, cached=cached, error_value=error_value)
        for prop in core.getDevicePropertyNames(device)
    }


def pixel_size_configs(core: CMMCorePlus) -> dict[PresetName, PixelSizeConfigDict]:
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
            "position": position(core),
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
