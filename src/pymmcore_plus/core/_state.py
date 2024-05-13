from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any, Literal, Sequence, TypedDict, cast

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class SystemInfoDict(TypedDict):
    APIVersionInfo: str
    BufferFreeCapacity: int
    BufferTotalCapacity: int
    CircularBufferMemoryFootprint: int
    DeviceAdapterSearchPaths: tuple[str, ...]
    PrimaryLogFile: str
    RemainingImageCount: int
    TimeoutMs: int  # rarely needed for metadata
    VersionInfo: str
    # these were removed in mmcore11 and probably shouldn't be used anyway
    # HostName: str
    # MACAddresses: tuple[str, ...]
    # UserId: str


class ImageDict(TypedDict):
    BytesPerPixel: int
    CurrentPixelSizeConfig: str
    Exposure: float
    ImageBitDepth: int
    ImageBufferSize: int
    ImageHeight: int
    ImageWidth: int
    MagnificationFactor: float
    MultiROI: tuple[list[int], list[int], list[int], list[int]] | None
    NumberOfCameraChannels: int
    NumberOfComponents: int
    PixelSizeAffine: tuple[float, float, float, float, float, float]
    PixelSizeUm: int
    ROI: list[int]


class PositionDict(TypedDict):
    X: float | None
    Y: float | None
    Focus: float | None


class AutoFocusDict(TypedDict):
    CurrentFocusScore: float
    LastFocusScore: float
    AutoFocusOffset: float | None


class PixelSizeConfigDict(TypedDict):
    Objective: dict[str, str]
    PixelSizeUm: float
    PixelSizeAffine: tuple[float, float, float, float, float, float]


class DeviceTypeDict(TypedDict):
    Type: str
    Description: str
    Adapter: str


class SystemStatusDict(TypedDict):
    debugLogEnabled: bool
    isBufferOverflowed: bool
    isContinuousFocusEnabled: bool
    isContinuousFocusLocked: bool
    isSequenceRunning: bool
    stderrLogEnabled: bool
    systemBusy: bool
    autoShutter: bool
    shutterOpen: bool


class StateDict(TypedDict, total=False):
    Devices: dict[str, dict[str, str]]
    SystemInfo: SystemInfoDict
    SystemStatus: SystemStatusDict
    ConfigGroups: dict[str, dict[str, Any]]
    Image: ImageDict
    Position: PositionDict
    AutoFocus: AutoFocusDict
    PixelSizeConfig: dict[str, str | PixelSizeConfigDict]
    DeviceTypes: dict[str, DeviceTypeDict]


def core_state(
    core: CMMCorePlus,
    *,
    devices: bool = True,
    image: bool = True,
    system_info: bool = False,
    system_status: bool = False,
    config_groups: bool | Sequence[str] = True,
    position: bool = False,
    autofocus: bool = False,
    pixel_size_configs: bool = False,
    device_types: bool = False,
    cached: bool = True,
    error_value: Any = None,
) -> StateDict:
    out: StateDict = {}
    if devices:
        out["Devices"] = get_device_state(core, error_value)
    if system_info:
        out["SystemInfo"] = get_system_info(core)
    if system_status:
        out["SystemStatus"] = get_system_status(core)
    if config_groups:
        out["ConfigGroups"] = get_config_groups(core, config_groups, cached)
    if image:
        out["Image"] = get_image_info(core, error_value)
    if position:
        out["Position"] = get_position(core, error_value)
    if autofocus:
        out["AutoFocus"] = get_autofocus(core, error_value)
    if pixel_size_configs:
        out["PixelSizeConfig"] = get_pix_size_config(core)
    if device_types:
        out["DeviceTypes"] = get_device_types(core)
    return out


def get_device_state(
    core: CMMCorePlus, cached: bool = True, error_value: Any = None
) -> dict[str, dict[str, Any]]:
    """Poulate 'Devices' key in StateDict."""
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


def get_system_info(core: CMMCorePlus) -> SystemInfoDict:
    """Populate 'SystemInfo' key in StateDict."""
    return {  # type: ignore
        key: getattr(core, f"get{key}")()
        for key in sorted(SystemInfoDict.__annotations__)
    }


def get_system_status(core: CMMCorePlus) -> SystemStatusDict:
    """Populate 'SystemStatus' key in StateDict."""
    out = {
        "autoShutter": core.getAutoShutter(),
        "shutterOpen": core.getShutterOpen(),
    }
    out.update(
        {
            key: getattr(core, key)()
            for key in sorted(SystemStatusDict.__annotations__)
            if key not in {"autoShutter", "shutterOpen"}
        }
    )
    return cast("SystemStatusDict", out)


def get_config_groups(
    core: CMMCorePlus,
    config_groups: bool | Sequence[str | Literal["[Channel]"]],
    cached: bool = True,
) -> dict[str, dict[str, Any]]:
    """Populate 'ConfigGroups' key in StateDict."""
    if not isinstance(config_groups, (list, tuple, set)):
        config_groups = core.getAvailableConfigGroups()

    getState = core.getConfigGroupStateFromCache if cached else core.getConfigGroupState
    curGrp = core.getCurrentConfigFromCache if cached else core.getCurrentConfig
    cfg_group_dict: dict = {}
    for grp in config_groups:
        if grp == "[Channel]":
            # special case for accessing channel group
            grp = core.getChannelGroup()

        grp_dict = cfg_group_dict.setdefault(grp, {})
        grp_dict["Current"] = curGrp(grp)

        for dev, prop, val in getState(grp):
            grp_dict.setdefault(dev, {})[prop] = val
    return cfg_group_dict


def get_image_info(core: CMMCorePlus, error_value: Any = None) -> ImageDict:
    """Populate 'Image' key in StateDict."""
    img_dict = {}
    for key in sorted(ImageDict.__annotations__):
        try:
            val = getattr(core, f"get{key}")()
        except Exception:
            val = error_value
        img_dict[key] = val
    return cast("ImageDict", img_dict)


def get_position(core: CMMCorePlus, error_value: Any = None) -> PositionDict:
    """Populate 'Position' key in StateDict."""
    pos: PositionDict = {"X": error_value, "Y": error_value, "Focus": error_value}
    with suppress(Exception):
        pos["X"] = core.getXPosition()
        pos["Y"] = core.getYPosition()
    with suppress(Exception):
        pos["Focus"] = core.getPosition()
    return pos


def get_autofocus(core: CMMCorePlus, error_value: Any = None) -> AutoFocusDict:
    """Populate 'AutoFocus' key in StateDict."""
    out: AutoFocusDict = {
        "CurrentFocusScore": core.getCurrentFocusScore(),
        "LastFocusScore": core.getLastFocusScore(),
        "AutoFocusOffset": error_value,
    }
    with suppress(Exception):
        out["AutoFocusOffset"] = core.getAutoFocusOffset()
    return out


def get_pix_size_config(core: CMMCorePlus) -> dict[str, str | PixelSizeConfigDict]:
    """Populate 'PixelSizeConfig' key in StateDict."""
    # the Current value is a string, all the rest are PixelSizeConfigDict
    px: dict = {"Current": core.getCurrentPixelSizeConfig()}
    for px_cfg_name in core.getAvailablePixelSizeConfigs():
        px_cfg_info: dict = {}
        for dev, prop, val in core.getPixelSizeConfigData(px_cfg_name):
            px_cfg_info.setdefault(dev, {})[prop] = val
        px_cfg_info["PixelSizeUm"] = core.getPixelSizeUmByID(px_cfg_name)
        px_cfg_info["PixelSizeAffine"] = core.getPixelSizeAffineByID(px_cfg_name)
        px[px_cfg_name] = px_cfg_info
    return px


def get_device_types(core: CMMCorePlus) -> dict[str, DeviceTypeDict]:
    """Populate 'DeviceTypes' key in StateDict."""
    return {
        dev_name: {
            "Type": core.getDeviceType(dev_name).name,
            "Description": core.getDeviceDescription(dev_name),
            "Adapter": core.getDeviceName(dev_name),
        }
        for dev_name in core.getLoadedDevices()
    }
