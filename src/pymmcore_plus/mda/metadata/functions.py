from __future__ import annotations

import datetime
from contextlib import suppress
from typing import TYPE_CHECKING

import pymmcore_plus
from pymmcore_plus.core._constants import DeviceType, PixelType

if TYPE_CHECKING:
    from typing import Unpack

    import useq

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


# -----------------------------------------------------------------
# These are the two main functions that are called from the outside
# -----------------------------------------------------------------


def summary_metadata(
    core: CMMCorePlus,
    *,
    mda_sequence: useq.MDASequence | None = None,
    cached: bool = True,
) -> SummaryMetaV1:
    """Return a summary metadata for the current state of the system."""
    summary: SummaryMetaV1 = {
        "format": "summary-dict-full",
        "version": "1.0",
        "devices": devices_info(core, cached=cached),
        "system_info": system_info(core),
        "image_infos": image_infos(core),
        "position": position(core),
        "config_groups": config_groups(core),
        "pixel_size_configs": pixel_size_configs(core),
        "datetime": _timestamp(),
    }
    if mda_sequence:
        summary["mda_sequence"] = mda_sequence
    return summary


def frame_metadata(
    core: CMMCorePlus, *, cached: bool = True, **kwargs: Unpack[FrameMetaV1]
) -> FrameMetaV1:
    """Return metadata for the current frame."""
    return {
        "format": "frame-dict-minimal",
        "version": "1.0",
        "exposure_ms": core.getExposure(),
        "pixel_size_um": core.getPixelSizeUm(cached),
        "position": position(core),
        **kwargs,
    }


# ----------------------------------------------
# supporting functions
# ----------------------------------------------


def _timestamp() -> str:
    """Return the current timestamp, try using local timezone, in ISO format."""
    now = datetime.datetime.now(tz=datetime.UTC)
    with suppress(Exception):
        now = now.astimezone()
    return now.isoformat()


def device_info(core: CMMCorePlus, *, label: str, cached: bool = True) -> DeviceInfo:
    """Return information about a specific device label."""
    devtype = core.getDeviceType(label)
    info: DeviceInfo = {
        "label": label,
        "library": core.getDeviceLibrary(label),
        "name": core.getDeviceName(label),
        "type": devtype.name,
        "description": core.getDeviceDescription(label),
        "properties": properties(core, device=label, cached=cached),
    }
    if parent := core.getParentLabel(label):
        info["parent_label"] = parent
    with suppress(RuntimeError):
        if devtype == DeviceType.Hub:
            info["child_names"] = core.getInstalledDevices(label)
        if devtype == DeviceType.State:
            info["labels"] = core.getStateLabels(label)
        elif devtype == DeviceType.Stage:
            info["is_sequenceable"] = core.isStageSequenceable(label)
            info["is_continuous_focus_drive"] = core.isContinuousFocusDrive(label)
            with suppress(RuntimeError):
                info["focus_direction"] = core.getFocusDirection(label).name  # type: ignore[typeddict-item]
        elif devtype == DeviceType.XYStage:
            info["is_sequenceable"] = core.isXYStageSequenceable(label)
        elif devtype == DeviceType.Camera:
            info["is_sequenceable"] = core.isExposureSequenceable(label)
        elif devtype == DeviceType.SLM:
            info["is_sequenceable"] = core.getSLMSequenceMaxLength(label) > 0
    return info


def system_info(core: CMMCorePlus) -> SystemInfo:
    """Return general system information."""
    return {
        "pymmcore_version": pymmcore_plus.__version__,
        "pymmcore_plus_version": pymmcore_plus.__version__,
        "mmcore_version": core.getVersionInfo(),
        "device_api_version": core.getAPIVersionInfo(),
        "device_adapter_search_paths": core.getDeviceAdapterSearchPaths(),
        "system_configuration_file": core.systemConfigurationFile(),
        "primary_log_file": core.getPrimaryLogFile(),
        "sequence_buffer_size_mb": core.getCircularBufferMemoryFootprint(),
        "continuous_focus_enabled": core.isContinuousFocusEnabled(),
        "continuous_focus_locked": core.isContinuousFocusLocked(),
        "auto_shutter": core.getAutoShutter(),
        # "timeout_ms": core.getTimeoutMs(),
    }


def image_info(core: CMMCorePlus) -> ImageInfo:
    """Return information about the current image properties."""
    w = core.getImageWidth()
    h = core.getImageHeight()
    n_comp = core.getNumberOfComponents()
    plane_shape: tuple[int, int] | tuple[int, int, int] = (h, w)
    if n_comp == 1:
        plane_shape = (h, w)
    elif n_comp == 4:
        plane_shape = (h, w, 3)
    else:
        plane_shape = (h, w, n_comp)
    bpp = core.getBytesPerPixel()
    dtype = f"uint{(bpp // n_comp) * 8}"

    info: ImageInfo = {
        "camera_label": core.getCameraDevice(),
        "plane_shape": plane_shape,
        "dtype": dtype,
        "image_height": h,
        "image_width": w,
        "bytes_per_pixel": bpp,
        "components_per_pixel": n_comp,
        "component_bit_depth": core.getImageBitDepth(),
        "pixel_format": PixelType.for_bytes(bpp, n_comp).value,
        "pixel_size_um": core.getPixelSizeUm(True),
        "pixel_size_config_name": core.getCurrentPixelSizeConfig(),
    }

    if (n_channels := core.getNumberOfCameraChannels()) > 1:
        info["num_camera_adapter_channels"] = n_channels
    if (mag_factor := core.getMagnificationFactor()) != 1.0:
        info["magnification_factor"] = mag_factor
    if (affine := core.getPixelSizeAffine(True)) != (1.0, 0.0, 0.0, 0.0, 1.0, 0.0):
        info["pixel_size_affine"] = affine  # type: ignore [typeddict-item]

    with suppress(RuntimeError):
        if (roi := core.getROI()) != [0, 0, info["image_width"], info["image_height"]]:
            info["roi"] = tuple(roi)  # type: ignore [typeddict-item]
    with suppress(RuntimeError):
        if any(rois := core.getMultiROI()):
            info["multi_roi"] = rois
    return info


def image_infos(core: CMMCorePlus) -> tuple[ImageInfo, ...]:
    """Return information about the current image properties for all cameras."""
    if not (loaded := core.getCameraDevice()):
        return ()
    # currently loaded device is always first
    infos: list[ImageInfo] = [image_info(core)]
    try:
        # load every other camera and get the image info
        for cam in core.getLoadedDevicesOfType(DeviceType.Camera):
            if cam != loaded:
                with suppress(RuntimeError):
                    core.setCameraDevice(cam)
                    infos.append(image_info(core))
    finally:
        # set the camera back to the original loaded device
        core.setCameraDevice(loaded)
    return tuple(infos)


def position(core: CMMCorePlus) -> Position:
    """Return current position."""
    x, y, z = None, None, None
    with suppress(Exception):
        x = core.getXPosition()
    with suppress(Exception):
        y = core.getYPosition()
    with suppress(Exception):
        z = core.getPosition()
    return {"x": x, "y": y, "z": z}


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
    info: PixelSizeConfigPreset = {
        "name": config_name,
        "pixel_size_um": core.getPixelSizeUmByID(config_name),
        "settings": tuple(
            {"dev": dev, "prop": prop, "val": val}
            for dev, prop, val in core.getPixelSizeConfigData(config_name)
        ),
    }
    affine = core.getPixelSizeAffineByID(config_name)
    if affine != (1.0, 0.0, 0.0, 0.0, 1.0, 0.0):
        info["pixel_size_affine"] = affine  # type: ignore [typeddict-item]
    return info


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
) -> PropertyInfo:
    """Return information on a specific device property."""
    try:
        if cached:
            value = core.getPropertyFromCache(device, prop)
        else:  # pragma: no cover
            value = core.getProperty(device, prop)
    except Exception:  # pragma: no cover
        value = None
    info: PropertyInfo = {
        "name": prop,
        "value": value,
        "data_type": core.getPropertyType(device, prop).__repr__(),
        "allowed_values": core.getAllowedPropertyValues(device, prop),
        "is_read_only": core.isPropertyReadOnly(device, prop),
    }
    if core.isPropertyPreInit(device, prop):
        info["is_pre_init"] = True
    if core.isPropertySequenceable(device, prop):
        info["sequenceable"] = True
        info["sequence_max_length"] = core.getPropertySequenceMaxLength(device, prop)
    if core.hasPropertyLimits(device, prop):
        info["limits"] = (
            core.getPropertyLowerLimit(device, prop),
            core.getPropertyUpperLimit(device, prop),
        )
    return info


def properties(
    core: CMMCorePlus, device: str, *, cached: bool = True
) -> tuple[PropertyInfo, ...]:
    """Return a dictionary of device properties values for all loaded devices."""
    # this actually appears to be faster than getSystemStateCache
    return tuple(
        property_info(core, device, prop, cached=cached)
        for prop in core.getDevicePropertyNames(device)
    )


def pixel_size_configs(core: CMMCorePlus) -> tuple[PixelSizeConfigPreset, ...]:
    """Return a dictionary of pixel size configurations."""
    return tuple(
        pixel_size_config(core, config_name=config_name)
        for config_name in core.getAvailablePixelSizeConfigs()
    )
