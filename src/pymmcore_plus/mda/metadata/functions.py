from __future__ import annotations

import datetime
from contextlib import suppress
from typing import TYPE_CHECKING, Any

import pymmcore_plus
from pymmcore_plus.core._constants import Keyword, PymmcPlusConstants

if TYPE_CHECKING:
    from pymmcore_plus.core import CMMCorePlus

    from .schema import (
        ConfigGroup,
        DeviceInfo,
        FrameMetaV1,
        ImageInfo,
        PixelSizeConfigPreset,
        Position,
        PropertyInfo,
        SummaryMetaV1,
        SystemInfo,
    )


def _now_isoformat() -> str:
    return datetime.datetime.now().isoformat()


def device_info(core: CMMCorePlus, *, label: str, cached: bool = True) -> DeviceInfo:
    """Return information about a specific device label."""
    info: DeviceInfo = {
        "label": label,
        "library": core.getDeviceLibrary(label),
        "name": core.getDeviceName(label),
        "type": core.getDeviceType(label).name,
        "description": core.getDeviceDescription(label),
        "parent_label": core.getParentLabel(label) or None,
        "properties": properties(core, device=label, cached=cached),
    }
    with suppress(RuntimeError):
        info["child_names"] = core.getInstalledDevices(label)
    with suppress(RuntimeError):
        info["focus_direction"] = core.getFocusDirection(label).name  # type: ignore[typeddict-item]
    with suppress(RuntimeError):
        info["labels"] = core.getStateLabels(label)
    return info


def system_info(core: CMMCorePlus) -> SystemInfo:
    """Return general system information."""
    return {
        "pymmcore_version": pymmcore_plus.__version__,
        "pymmcore_plus_version": pymmcore_plus.__version__,
        "mmcore_version": core.getVersionInfo(),
        "device_api_version": core.getAPIVersionInfo(),
        "device_adapter_search_paths": core.getDeviceAdapterSearchPaths(),
        "system_configuration": core.systemConfigurationFile(),
        "primary_log_file": core.getPrimaryLogFile(),
        "circular_buffer_memory_footprint": core.getCircularBufferMemoryFootprint(),
        "buffer_total_capacity": core.getBufferTotalCapacity(),
        "buffer_free_capacity": core.getBufferFreeCapacity(),
        "timeout_ms": core.getTimeoutMs(),
        # "remaining_image_count": core.getRemainingImageCount(),
    }


def image_info(core: CMMCorePlus) -> ImageInfo:
    """Return information about the current image properties."""
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


def position(core: CMMCorePlus) -> Position:
    """Return current position."""
    x, y, focus = None, None, None
    with suppress(Exception):
        x = core.getXPosition()
        y = core.getYPosition()
    with suppress(Exception):
        focus = core.getPosition()
    return {"x": x, "y": y, "focus": focus}


def config_group(core: CMMCorePlus, *, group_name: str) -> ConfigGroup:
    """Return a dictionary of configuration presets for a specific group."""
    return {
        "name": group_name,
        "presets": tuple(
            {
                "name": preset_name,
                "settings": tuple(
                    {"dev": dev, "prop": prop, "val": val}
                    for dev, prop, val in core.getConfigData(group_name, preset_name)
                ),
            }
            for preset_name in core.getAvailableConfigs(group_name)
        ),
    }


def config_groups(core: CMMCorePlus) -> tuple[ConfigGroup, ...]:
    """Return all configuration groups."""
    return tuple(
        config_group(core, group_name=group_name)
        for group_name in core.getAvailableConfigGroups()
    )


def pixel_size_config(core: CMMCorePlus, *, config_name: str) -> PixelSizeConfigPreset:
    """Return info for a specific pixel size preset for a specific."""
    return {
        "name": config_name,
        "pixel_size_um": core.getPixelSizeUmByID(config_name),
        "pixel_size_affine": core.getPixelSizeAffineByID(config_name),  # type: ignore
        "settings": tuple(
            {"dev": dev, "prop": prop, "val": val}
            for dev, prop, val in core.getPixelSizeConfigData(config_name)
        ),
    }


def summary_metadata(core: CMMCorePlus, extra: dict[str, Any]) -> SummaryMetaV1:
    """Return a summary metadata for the current state of the system."""
    summary: SummaryMetaV1 = {
        "devices": devices_info(core, cached=extra.get("cached", True)),
        "system_info": system_info(core),
        "image_info": image_info(core),
        "position": position(core),
        "config_groups": config_groups(core),
        "pixel_size_configs": pixel_size_configs(core),
        "format": "summary-struct-full",
        "date_time": _now_isoformat(),
        "version": "1.0",
    }
    if mda_sequence := extra.get(PymmcPlusConstants.MDA_SEQUENCE.value):
        summary["mda_sequence"] = mda_sequence
    return summary


def devices_info(core: CMMCorePlus, cached: bool = True) -> tuple[DeviceInfo, ...]:
    """Return a dictionary of device information for all loaded devices."""
    return tuple(
        device_info(core, label=lbl, cached=cached) for lbl in core.getLoadedDevices()
    )


def property_info(
    core: CMMCorePlus,
    device: str,
    prop: str,
    *,
    cached: bool = True,
    error_value: Any = None,
) -> PropertyInfo:
    """Return information on a specific device property."""
    try:
        if cached:
            value = core.getPropertyFromCache(device, prop)
        else:
            value = core.getProperty(device, prop)
    except Exception:
        value = error_value
    info: PropertyInfo = {
        "name": prop,
        "value": value,
        "data_type": core.getPropertyType(device, prop).__repr__(),
        "allowed_values": core.getAllowedPropertyValues(device, prop),
        "is_read_only": core.isPropertyReadOnly(device, prop),
        "is_pre_init": core.isPropertyPreInit(device, prop),
        "sequenceable": core.isPropertySequenceable(device, prop),
    }

    if core.hasPropertyLimits(device, prop):
        info["limits"] = (
            core.getPropertyLowerLimit(device, prop),
            core.getPropertyUpperLimit(device, prop),
        )
    if info["sequenceable"]:
        info["sequence_max_length"] = core.getPropertySequenceMaxLength(device, prop)
    return info


def properties(
    core: CMMCorePlus, device: str, cached: bool = True, error_value: Any = None
) -> tuple[PropertyInfo, ...]:
    """Return a dictionary of device properties values for all loaded devices."""
    # this actually appears to be faster than getSystemStateCache
    return tuple(
        property_info(core, device, prop, cached=cached, error_value=error_value)
        for prop in core.getDevicePropertyNames(device)
    )


def pixel_size_configs(core: CMMCorePlus) -> tuple[PixelSizeConfigPreset, ...]:
    """Return a dictionary of pixel size configurations."""
    return tuple(
        pixel_size_config(core, config_name=config_name)
        for config_name in core.getAvailablePixelSizeConfigs()
    )


def frame_metadata(core: CMMCorePlus, extra: dict[str, Any]) -> FrameMetaV1:
    """Return metadata for the current frame."""
    meta: FrameMetaV1 = {
        "exposure_ms": core.getExposure(),
        "pixel_size_um": core.getPixelSizeUm(extra.get("cached", True)),
        "position": position(core),
        "camera_device": extra.get(Keyword.CoreCamera.value),
        "config_state": extra.get(PymmcPlusConstants.CONFIG_STATE.value),
        "format": "frame-dict-minimal",
        "version": "1.0",
    }

    if mda_event := extra.get(PymmcPlusConstants.MDA_EVENT.value):
        meta["mda_event"] = mda_event
        if run_time := mda_event.metadata.get(PymmcPlusConstants.RUNNER_TIME_SEC.value):
            meta["runner_time"] = run_time
    return meta
