from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any, TypedDict

import pymmcore_plus
from pymmcore_plus._util import timestamp
from pymmcore_plus.core._constants import DeviceType, PixelFormat

if TYPE_CHECKING:
    import useq
    from typing_extensions import Unpack

    from pymmcore_plus.core import CMMCorePlus

    from .schema import (
        ConfigGroup,
        DeviceInfo,
        FrameMetaV1,
        ImageInfo,
        PixelSizeConfigPreset,
        Position,
        PropertyInfo,
        PropertyValue,
        StagePosition,
        SummaryMetaV1,
        SystemInfo,
    )

    class _OptionalFrameMetaKwargs(TypedDict, total=False):
        """Additional optional fields for frame metadata."""

        mda_event: useq.MDAEvent
        hardware_triggered: bool
        images_remaining_in_buffer: int
        camera_metadata: dict[str, Any]
        extra: dict[str, Any]
        position: Position

# -----------------------------------------------------------------
# These are the two main functions that are called from the outside
# -----------------------------------------------------------------


def summary_metadata(
    core: CMMCorePlus,
    *,
    mda_sequence: useq.MDASequence | None = None,
    cached: bool = True,
    include_time: bool = True,
) -> SummaryMetaV1:
    """Return a summary metadata for the current state of the system.

    See [pymmcore_plus.metadata.SummaryMetaV1][] for a description of the
    dictionary format.
    """
    summary: SummaryMetaV1 = {
        "format": "summary-dict",
        "version": "1.0",
        "devices": devices_info(core, cached=cached),
        "system_info": system_info(core),
        "image_infos": image_infos(core),
        "position": position(core),
        "config_groups": config_groups(core),
        "pixel_size_configs": pixel_size_configs(core),
    }
    if include_time:
        summary["datetime"] = timestamp()
    if mda_sequence:
        summary["mda_sequence"] = mda_sequence
    return summary


def frame_metadata(
    core: CMMCorePlus,
    *,
    cached: bool = True,
    runner_time_ms: float = -1,
    camera_device: str | None = None,
    property_values: tuple[PropertyValue, ...] = (),
    include_position: bool = False,
    **kwargs: Unpack[_OptionalFrameMetaKwargs],
) -> FrameMetaV1:
    """Return metadata for the current frame."""
    info: FrameMetaV1 = {
        "format": "frame-dict",
        "version": "1.0",
        "runner_time_ms": runner_time_ms,
        "camera_device": camera_device or core.getPhysicalCameraDevice(),
        "property_values": property_values,
        "exposure_ms": core.getExposure(),
        "pixel_size_um": core.getPixelSizeUm(cached),
        **kwargs,
    }
    if include_position and "position" not in kwargs:
        info["position"] = position(core)
    return info


# ----------------------------------------------
# supporting functions
# ----------------------------------------------


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
        "timeout_ms": core.getTimeoutMs(),
    }


def image_info(core: CMMCorePlus) -> ImageInfo:
    """Return information about the current camera image properties."""
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
        "height": h,
        "width": w,
        "pixel_format": PixelFormat.for_current_camera(core).value,
        "pixel_size_um": core.getPixelSizeUm(True),
        "pixel_size_config_name": core.getCurrentPixelSizeConfig(),
    }

    # if (n_channels := core.getNumberOfCameraChannels()) > 1:
    #     info["num_camera_adapter_channels"] = n_channels
    if (mag_factor := core.getMagnificationFactor()) != 1.0:
        info["magnification_factor"] = mag_factor
    if (affine := core.getPixelSizeAffine(True)) != (1.0, 0.0, 0.0, 0.0, 1.0, 0.0):
        info["pixel_size_affine"] = affine

    with suppress(RuntimeError):
        if (roi := core.getROI()) != [0, 0, w, h]:
            info["roi"] = tuple(roi)  # type: ignore [typeddict-item]
    with suppress(RuntimeError):
        if any(rois := core.getMultiROI()):
            info["multi_roi"] = rois
    return info


def image_infos(core: CMMCorePlus) -> tuple[ImageInfo, ...]:
    """Return information about the current image properties for all cameras."""
    if not (selected := core.getCameraDevice()):
        return ()
    # currently selected device is always first
    infos: list[ImageInfo] = [image_info(core)]
    try:
        # set every other camera and get the image info
        for cam in core.getLoadedDevicesOfType(DeviceType.Camera):
            if cam != selected:
                with suppress(RuntimeError):
                    core.setCameraDevice(cam)
                    infos.append(image_info(core))
    finally:
        # set the camera back to the originally selected device
        core.setCameraDevice(selected)
    return tuple(infos)


def position(core: CMMCorePlus, all_stages: bool = False) -> Position:
    """Return current position of active (and, optionally, all) stages."""
    position: Position = {}

    try:
        # single shot faster when it works
        position["x"], position["y"] = core.getXYPosition()
    except RuntimeError:
        with suppress(Exception):
            position["x"] = core.getXPosition()
        with suppress(Exception):
            position["y"] = core.getYPosition()

    with suppress(Exception):
        position["z"] = core.getPosition()

    if all_stages:
        pos_list: list[StagePosition] = []
        for stage in core.getLoadedDevicesOfType(DeviceType.Stage):
            with suppress(Exception):
                pos_list.append(
                    {
                        "device_label": stage,
                        "position": core.getPosition(stage),
                    }
                )
        for stage in core.getLoadedDevicesOfType(DeviceType.XYStage):
            with suppress(Exception):
                pos_list.append(
                    {
                        "device_label": stage,
                        "position": tuple(core.getXYPosition(stage)),  # type: ignore
                    }
                )
        position["all_stages"] = pos_list
    return position


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
        info["pixel_size_affine"] = affine
    # added in v11.5
    if hasattr(core, "getPixelSizedxdz") and (px := core.getPixelSizedxdz(config_name)):
        info["pixel_size_dxdz"] = px
    if hasattr(core, "getPixelSizedydz") and (px := core.getPixelSizedydz(config_name)):
        info["pixel_size_dydz"] = px
    if hasattr(core, "getPixelSizeOptimalZUm") and (
        z := core.getPixelSizeOptimalZUm(config_name)
    ):
        info["pixel_size_optimal_z_um"] = z
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
