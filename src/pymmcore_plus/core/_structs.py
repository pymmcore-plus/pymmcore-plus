from __future__ import annotations

import datetime
import sys
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Literal

import msgspec
from msgspec import Struct, field

from pymmcore_plus.mda._runner import TIME_KEY

if TYPE_CHECKING:
    from typing import Self, TypeAlias

    import useq

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


def _enc_hook(obj: Any) -> Any:
    pydantic = sys.modules.get("pydantic")
    if pydantic and isinstance(obj, pydantic.BaseModel):
        try:
            return obj.model_dump(mode="json")
        except AttributeError:
            return obj.dict()

    # Raise a NotImplementedError for other types
    raise NotImplementedError(f"Objects of type {type(obj)!r} are not supported")


def _dec_hook(type: type, obj: Any) -> Any:
    # `type` here is the value of the custom type annotation being decoded.
    if TYPE_CHECKING:
        import pydantic
    else:
        pydantic = sys.modules.get("pydantic")
    if pydantic and issubclass(type, pydantic.BaseModel):
        try:
            return type.model_validate(obj)
        except AttributeError:
            return type.parse_obj(obj)

    # Raise a NotImplementedError for other types
    raise NotImplementedError(f"Objects of type {type!r} are not supported")


class PyMMCoreStruct(Struct):
    """Convenience methods for structs, following Pydantic API (just in case)."""

    def model_dump(self) -> dict[str, Any]:
        """Convert the struct to a dictionary."""
        return msgspec.to_builtins(self, enc_hook=_enc_hook)  # type: ignore

    @classmethod
    def model_validate(cls, obj: Any, *, strict: bool = True) -> Self:
        """Create a struct from a dictionary."""
        return msgspec.convert(obj, cls, strict=strict, dec_hook=_dec_hook)

    def model_dump_json(self, *, indent: int | None = None) -> bytes:
        """Convert the struct to a JSON string."""
        data = msgspec.json.encode(self, enc_hook=_enc_hook)
        if indent is not None:
            return msgspec.json.format(data, indent=indent)
        return data

    @classmethod
    def model_validate_json(
        cls, json_data: bytes | str, *, strict: bool = True
    ) -> Self:
        """Create struct from JSON bytes or string."""
        return msgspec.json.decode(
            json_data, type=cls, strict=strict, dec_hook=_dec_hook
        )

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
    def from_core(cls, core: CMMCorePlus, *, label: str) -> Self:
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
    def from_core(cls, core: CMMCorePlus) -> Self:
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
    def from_core(cls, core: CMMCorePlus) -> Self:
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
    def from_core(cls, core: CMMCorePlus) -> Self:
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
    def from_core(cls, core: CMMCorePlus, *, config_name: str) -> Self:
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
    mda_sequence: useq.MDASequence | None = None
    date_time: str = field(default_factory=_now_isoformat)
    format: Literal["summary"] = Format.SUMMARY_FULL
    version: Literal["1.0"] = "1.0"

    @classmethod
    def from_core(cls, core: CMMCorePlus, extra: dict[str, Any]) -> Self:
        return cls(
            devices=_devices_info(core),
            properties=_properties_state(core, cached=extra.get("cached", True)),
            system_info=SystemInfo.from_core(core),
            image_info=ImageInfo.from_core(core),
            position=PositionInfo.from_core(core),
            pixel_size_configs=_pixel_size_configs(core),
            mda_sequence=extra.get("mda_sequence"),
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
    mda_event: useq.MDAEvent | None = None
    seconds_elapsed: float | None = None
    physical_camera_device: str | None = None
    config_state: dict[str, dict[str, Any]] | None = None

    format: Literal["frame"] = Format.FRAME
    version: Literal["1.0"] = "1.0"

    @classmethod
    def from_core(cls, core: CMMCorePlus, extra: dict[str, Any]) -> Self:
        if event := extra.get("mda_event"):
            seconds_elapsed = event.metadata.get(TIME_KEY)
        else:
            seconds_elapsed = None
        return cls(
            exposure_ms=core.getExposure(),
            pixel_size_um=core.getPixelSizeUm(extra.get("cached", True)),
            position=PositionInfo.from_core(core),
            mda_event=event,
            seconds_elapsed=seconds_elapsed,
            physical_camera_device=extra.get("physical_camera_device"),
            config_state=extra.get("config_state"),
        )
