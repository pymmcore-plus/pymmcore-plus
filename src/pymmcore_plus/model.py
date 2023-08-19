from __future__ import annotations

import datetime
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Generic, Iterator, NamedTuple

from pymmcore_plus import (
    CFGCommand,
    CFGGroup,
    DeviceType,
    FocusDirection,
    Keyword,
    PropertyType,
)

from ._util import no_stdout

if TYPE_CHECKING:
    import builtins
    from typing import TypeVar

    from pymmcore import CMMCore
    from typing_extensions import Self

    from pymmcore_plus import CMMCorePlus

    D = TypeVar("D", bound="Device")
    ConfigPresetType = TypeVar("ConfigPresetType", bound="ConfigPreset")

__all__ = [
    "ConfigGroup",
    "ConfigPreset",
    "CoreDevice",
    "Device",
    "HubDevice",
    "Microscope",
    "PropertyItem",
    "SerialDevice",
    "Setting",
    "StageDevice",
    "StateDevice",
]

UNDEFINED = "UNDEFINED"
DEFAULT_AFFINE = (1, 0, 0, 0, 1, 0)


def _cfg_field(*args: Any) -> str:
    return CFGCommand.FieldDelimiters.join(map(str, args))


def _prop_field(*args: Any) -> str:
    return _cfg_field(CFGCommand.Property, *args)


@dataclass
class PropertyItem:
    """Model of a device property."""

    device: str
    name: str
    value: str
    read_only: bool = False
    pre_init: bool = False
    allowed: tuple[str, ...] = field(default_factory=tuple)
    has_limits: bool = False
    lower_limit: float = 0.0
    upper_limit: float = 0.0
    type: PropertyType = PropertyType.Undef
    device_type: DeviceType = DeviceType.Unknown
    use_in_setup: bool = False  # setupProperties_

    @classmethod
    def create_from_core(
        cls,
        core: CMMCore,
        device_name: str,
        property_name: str,
        cached: bool = False,
    ) -> Self:
        """Create a DeviceProperty populated with current core values."""
        getValue = core.getPropertyFromCache if cached else core.getProperty
        return cls(
            device=device_name,
            name=property_name,
            value=getValue(device_name, property_name),
            read_only=core.isPropertyReadOnly(device_name, property_name),
            pre_init=core.isPropertyPreInit(device_name, property_name),
            # sort these?
            allowed=tuple(core.getAllowedPropertyValues(device_name, property_name)),
            has_limits=core.hasPropertyLimits(device_name, property_name),
            lower_limit=core.getPropertyLowerLimit(device_name, property_name),
            upper_limit=core.getPropertyUpperLimit(device_name, property_name),
            type=PropertyType(core.getPropertyType(device_name, property_name)),
            device_type=DeviceType(core.getDeviceType(device_name)),
        )

    def to_cfg(self) -> str:
        """Return a config string for this property."""
        return _prop_field(self.device, self.name, self.value)


@dataclass
class Device:
    """Model of a device."""

    name: str
    library: str
    adapter_name: str
    description: str = ""
    type: DeviceType = DeviceType.Any  # perhaps UnknownType?
    properties: list[PropertyItem] = field(default_factory=list)
    delay_ms: float = 0.0
    uses_delay: bool = False
    parent_name: str | None = None
    initialized: bool = False

    @classmethod
    def create_from_core(cls, core: CMMCore, device_name: str) -> Device:
        """Create a Device populated with current core values."""
        type_ = core.getDeviceType(device_name)
        dev = _dev_subcls(type_)(
            name=device_name,
            library=core.getDeviceLibrary(device_name),
            adapter_name=core.getDeviceName(device_name),
            type=DeviceType(type_),
            delay_ms=core.getDeviceDelayMs(device_name),
        )
        dev.update_from_core(core)  # let subclass update specific values
        return dev

    def update_from_core(self, core: CMMCore) -> None:
        """Update the Device with current core values."""
        if DeviceType(core.getDeviceType(self.name)) != self.type:
            raise ValueError("Device Type mismatch")  # pragma: no cover
        self.properties = [
            PropertyItem.create_from_core(core, self.name, prop_name)
            for prop_name in core.getDevicePropertyNames(self.name)
        ]
        self.description = core.getDeviceDescription(self.name)
        self.uses_delay = core.usesDeviceDelay(self.name)
        self.parent_name = core.getParentLabel(self.name)

        # NOTE: from MMStudio: do not load the delay value from the hardware
        # we will always use settings defined in the config file
        # self.delay_ms = core.getDeviceDelayMs(self.name)

    @staticmethod
    def library_contents(core: CMMCore, library_name: str) -> tuple[Device, ...]:
        """Return a tuple of Devices in the given library."""
        with no_stdout():
            devs = core.getAvailableDevices(library_name)
        types = core.getAvailableDeviceTypes(library_name)
        descriptions = core.getAvailableDeviceDescriptions(library_name)
        return tuple(
            _dev_subcls(dev_type)(
                name=UNDEFINED,
                library=library_name,
                adapter_name=dev_name,
                description=desc,
                type=DeviceType(dev_type),
            )
            for dev_name, dev_type, desc in zip(devs, types, descriptions)
        )

    def find_property(self, prop_name: str) -> PropertyItem | None:
        """Find a property by name."""
        return next((p for p in self.properties if p.name == prop_name), None)

    def set_default_prop(
        self, prop_name: str, value: str = "", **kwargs: Any
    ) -> PropertyItem:
        """Works similar to `dict.set_default`. Add property if it doesn't exist."""
        if not (prop := self.find_property(prop_name)):
            prop = PropertyItem(self.name, prop_name, value, **kwargs)
            self.properties.append(prop)
        return prop

    def pre_init_props(self) -> Iterator[PropertyItem]:
        """Return a list of pre-init properties."""
        yield from (p for p in self.properties if p.pre_init)

    def setup_props(self) -> Iterator[PropertyItem]:
        """Return a list of properties to be used in setup."""
        yield from (p for p in self.properties if p.use_in_setup)

    def to_cfg(self) -> str:
        """Return a config string for this device."""
        return _cfg_field(CFGCommand.Device, self.name, self.library, self.adapter_name)

    @classmethod
    def from_device(cls: builtins.type[D], dev: Device) -> D:
        """For subclasses to promote a Device."""
        return cls(
            name=dev.name,
            library=dev.library,
            adapter_name=dev.adapter_name,
            description=dev.description,
            delay_ms=dev.delay_ms,
            properties=dev.properties,
            uses_delay=dev.uses_delay,
            parent_name=dev.parent_name,
        )


# could use __new__ ... but it's not really necessary
def _dev_subcls(type: DeviceType | int) -> builtins.type[Device]:
    return {
        DeviceType.Hub: HubDevice,
        DeviceType.Stage: StageDevice,
        DeviceType.State: StateDevice,
        DeviceType.Serial: SerialDevice,
        DeviceType.Core: CoreDevice,
    }.get(DeviceType(type), Device)


@dataclass
class HubDevice(Device):
    """Model of a hub device.""."""

    children: tuple[str, ...] = field(default_factory=tuple)
    type: DeviceType = DeviceType.Hub

    def update_from_core(self, core: CMMCore) -> None:
        """Update the HubDevice with current core values."""
        self.children = tuple(core.getInstalledDevices(self.name))


@dataclass
class StageDevice(Device):
    """Model of a stage device."""

    focus_direction: FocusDirection = FocusDirection.Unknown
    type: DeviceType = DeviceType.Stage

    def update_from_core(self, core: CMMCore) -> None:
        """Update the StateDevice with current core values."""
        super().update_from_core(core)
        self.focus_direction = FocusDirection(core.getFocusDirection(self.name))

    def focus_cfg(self) -> str:
        """Output config string."""
        return _cfg_field(
            CFGCommand.FocusDirection, self.name, self.focus_direction.value
        )


@dataclass
class StateDevice(Device):
    """Model of a state device."""

    # map of state index to label
    labels: dict[int, str] = field(default_factory=dict)
    type: DeviceType = DeviceType.State

    def update_from_core(self, core: CMMCore) -> None:
        """Update the StateDevice with current core values."""
        super().update_from_core(core)
        self.labels = dict(enumerate(core.getStateLabels(self.name)))

    def labels_cfg(self) -> list[str]:
        """Return a list of config strings for this device's labels."""
        return [
            _cfg_field(CFGCommand.Label, self.name, state, label)
            for state, label in self.labels.items()
        ]


@dataclass
class SerialDevice(Device):
    """Model of the core device."""

    type: DeviceType = DeviceType.Serial

    def __post_init__(self) -> None:
        """Validate the SerialDevice."""
        if self.name == UNDEFINED:
            self.name = self.adapter_name


@dataclass
class CoreDevice(Device):
    """Model of the core device."""

    name: str = Keyword.CoreDevice
    library: str = ""
    adapter_name: str = "MMCore"
    type: DeviceType = DeviceType.Core
    description = "Core device"

    def __post_init__(self) -> None:
        """Add core properties if they don't exist."""
        self.set_default_prop(Keyword.CoreCamera, use_in_setup=True)
        self.set_default_prop(Keyword.CoreShutter, use_in_setup=True)
        self.set_default_prop(Keyword.CoreFocus, use_in_setup=True)
        self.set_default_prop(Keyword.CoreAutoShutter, "1", use_in_setup=True)

    def roles(self) -> list[str]:
        """Return the roles of this device."""
        return [
            prop.to_cfg()
            for field in (
                Keyword.CoreCamera,
                Keyword.CoreShutter,
                Keyword.CoreFocus,
                Keyword.CoreAutoShutter,
            )
            if (prop := self.find_property(field))
        ]


class Setting(NamedTuple):
    """Model of a device setting."""

    device_name: str = UNDEFINED
    property_name: str = UNDEFINED
    property_value: str = UNDEFINED

    # def matches(self, other: Setting) -> bool:
    #     """Return True if this Setting matches the given device and property."""
    #     return (
    #         self.device_name == other.device_name
    #         and self.property_name == other.property_name
    #     )


@dataclass
class ConfigPreset:
    """ConfigPreset model."""

    name: str
    settings: list[Setting] = field(default_factory=list)


@dataclass
class PixelSizePreset(ConfigPreset):
    """PixelSizePreset model."""

    pixel_size_um: float = 0.0
    affine_transform: tuple[float, ...] = DEFAULT_AFFINE


@dataclass
class ConfigGroup(Generic[ConfigPresetType]):
    """ConfigGroup model."""

    name: str
    presets: dict[str, ConfigPresetType] = field(default_factory=dict)

    def to_cfg(self) -> list[str]:
        """Return a config string for this ConfigGroup."""
        out = [f"# Group: {self.name}"]
        for preset in self.presets.values():
            out.append(f"# Preset: {preset.name}")
            out.extend(
                _cfg_field(CFGCommand.ConfigGroup, self.name, preset.name, *s)
                for s in preset.settings
            )
        return out


@dataclass
class PixelSizeGroup(ConfigGroup[PixelSizePreset]):
    """Model of the pixel size group."""

    name: str = "PixelSizeGroup"
    presets: dict[str, PixelSizePreset] = field(default_factory=dict)

    @classmethod
    def create_from_core(cls, core: CMMCorePlus) -> PixelSizeGroup:
        """Create pixel size presets from the given core."""
        return cls(
            presets={
                preset: PixelSizePreset(
                    name=preset,
                    pixel_size_um=core.getPixelSizeUmByID(preset),
                    affine_transform=core.getPixelSizeAffineByID(preset),
                    settings=[Setting(*d) for d in core.getPixelSizeConfigData(preset)],
                )
                for preset in core.getAvailablePixelSizeConfigs()
            }
        )

    def to_cfg(self) -> list[str]:
        """Return a config string for this PixelSizeGroup."""
        out = []
        for p in self.presets.values():
            out.append(f"# Resolution preset: {p.name}")
            out.extend(
                _cfg_field(CFGCommand.ConfigPixelSize, p.name, *setting)
                for setting in p.settings
            )
            out.append(_cfg_field(CFGCommand.PixelSize_um, p.name, p.pixel_size_um))
            if p.affine_transform != DEFAULT_AFFINE:
                out.append(
                    _cfg_field(CFGCommand.PixelSizeAffine, p.name, *p.affine_transform)
                )
        return out


@dataclass
class Microscope:
    """Full model of a microscope."""

    devices: list[Device] = field(default_factory=list)
    config_groups: dict[str, ConfigGroup] = field(default_factory=dict)
    pixel_size_group: PixelSizeGroup = field(default_factory=PixelSizeGroup)
    # config_groups: dict[str, dict[str, list[tuple]]] = field(default_factory=dict)
    available_devices: tuple[Device, ...] = field(default_factory=tuple)
    available_com_ports: tuple[Device, ...] = field(default_factory=tuple)
    assigned_com_ports: dict[str, Device] = field(default_factory=dict)
    config_file: str = ""

    def __post_init__(self) -> None:
        """Validate and initialized the Microscope."""
        # Used during load_from_file to check whether the init step has been run
        self._initialized: bool = False

        # ensure core device exists:
        if not any(isinstance(d, CoreDevice) for d in self.devices):
            self.devices.append(CoreDevice())

        # ensure system configs:
        sys_cfgs: list[tuple[str, tuple[str, ...]]] = [
            (CFGGroup.System, (CFGGroup.System_Startup,)),
            (Keyword.Channel, ()),
        ]
        for cfg_grp, presets in sys_cfgs:
            cg = self.config_groups.setdefault(cfg_grp, ConfigGroup(name=cfg_grp))
            for preset in presets:
                cg.presets.setdefault(preset, ConfigPreset(name=preset))

    def reset(self) -> None:
        """Reset the Microscope to its initial state."""
        defaults = Microscope()
        for f in fields(self):
            setattr(self, f.name, getattr(defaults, f.name))

    def find_device(self, device_name: str) -> Device:
        """Find a device by name or raise ValueError."""
        for d in self.devices:
            if d.name == device_name:
                return d
        raise ValueError(f"Device {device_name!r} not defined")

    @classmethod
    def create_from_core(cls, core: CMMCorePlus) -> Microscope:
        """Create a Microscope populated with current core values."""
        obj = cls()
        obj.update_from_core(core)
        return obj

    def update_from_core(self, core: CMMCorePlus) -> None:
        """Update the Microscope with current core values."""
        for device_name in core.getLoadedDevices():
            try:
                self.find_device(device_name).update_from_core(core)
            except ValueError:
                dev = Device.create_from_core(core, device_name)
                self.devices.append(dev)

        self.update_available_devices(core)
        self.load_configs_from_core(core)
        self.load_pixel_sizes_from_core(core)

    def load_configs_from_core(self, core: CMMCorePlus) -> None:
        """Populate the config_groups with current core values."""
        self.config_groups.clear()
        for group_name in core.getAvailableConfigGroups():
            self.config_groups[group_name] = ConfigGroup(
                name=group_name,
                presets={
                    preset: ConfigPreset(
                        name=preset,
                        settings=[
                            Setting(*d) for d in core.getConfigData(group_name, preset)
                        ],
                    )
                    for preset in core.getAvailableConfigs(group_name)
                },
            )

    def load_pixel_sizes_from_core(self, core: CMMCorePlus) -> None:
        """Load the pixel sizes from the core."""
        self.pixel_size_group = PixelSizeGroup.create_from_core(core)

    def update_available_devices(self, core: CMMCore) -> None:
        """Return a tuple of available Devices."""
        devs: list[Device] = []
        com_ports: list[Device] = []
        for lib_name in core.getDeviceAdapterNames():
            # should we be excluding serial ports here? like MMStudio?
            for dev in Device.library_contents(core, lib_name):
                if dev.type == DeviceType.Serial:
                    com_ports.append(dev)
                else:
                    devs.append(dev)
        self.available_devices = tuple(devs)
        self.available_com_ports = tuple(com_ports)

    @property
    def core(self) -> CoreDevice:
        """Return the CoreDevice."""
        return next(d for d in self.devices if isinstance(d, CoreDevice))

    @property
    def hubs(self) -> tuple[HubDevice, ...]:
        """Return a tuple of HubDevices."""
        return tuple(d for d in self.available_devices if isinstance(d, HubDevice))

    def save(self, path: str | Path) -> None:
        """Save model as a micro-manager config file."""
        Path(path).expanduser().resolve().write_text(self.dump_to_string())

    def dump_to_string(self) -> str:
        """Save the Microscope to a file."""
        # Fri Aug 18 07:16:46 EDT 2023
        now = datetime.datetime.now(datetime.timezone.utc)
        date = now.astimezone().strftime("%a %b %d %H:%M:%S %Z %Y")

        devices: list[str] = []
        pre_init_settings: list[str] = []
        hub_refs: list[str] = []
        delays: list[str] = []
        focus_directions: list[str] = []
        labels = []

        # TODO: add in-use com-port settings
        for d in self.devices:
            if d.type == DeviceType.Core:
                continue
            devices.append(d.to_cfg())
            pre_init_settings.extend(p.to_cfg() for p in d.pre_init_props())
            if d.parent_name:
                hub_refs.append(_cfg_field(CFGCommand.ParentID, d.name, d.parent_name))
            if d.delay_ms:
                delays.append(_cfg_field(CFGCommand.Delay, d.name, d.delay_ms))
            if isinstance(d, StageDevice):
                focus_directions.append(d.focus_cfg())
            if isinstance(d, StateDevice) and d.labels:
                labels.append(f"# {d.name}")
                # NOTE: MMStudio reverses the order
                labels.extend(d.labels_cfg())
        configs = []
        for group in self.config_groups.values():
            configs.extend([*group.to_cfg(), ""])

        return CFG_TEMPLATE.format(
            date=date,
            devices="\n".join(devices),
            pre_init_settings="\n".join(pre_init_settings),
            pre_init_com_settings="",
            hub_refs="\n".join(hub_refs),
            delays="\n".join(delays),
            focus_directions="\n".join(focus_directions),
            roles="\n".join(self.core.roles()),
            camera_synced_devices="",
            labels="\n".join(labels),
            config_presets="\n".join(configs),
            pixel_size_settings="\n".join(self.pixel_size_group.to_cfg()),
        )

    def load(self, path: str | Path) -> None:
        """Save model as a micro-manager config file."""
        path = Path(path).expanduser().resolve()
        self.load_from_string(path.read_text())
        self.config_file = str(path)

    def load_from_string(self, text: str) -> None:
        """Load the Microscope from a string."""
        self.reset()

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cmd, *args = line.split(CFGCommand.FieldDelimiters)
            try:
                method = self._CMD_MAP[CFGCommand(cmd)]
            except ValueError as exc:
                raise ValueError(
                    f"Error parsing line: {line!r}. (Invalid command name {cmd!r})"
                ) from exc
            except KeyError as exc:
                raise ValueError(
                    f"Error parsing line: {line!r}. (Cannot process command: {cmd!r})"
                ) from exc

            try:
                method(self, *args)
            except Exception as exc:
                raise ValueError(f"Bad arguments in line {line!r}: {exc}") from exc

    def _cmd_device(self, name: str, library: str, adapter_name: str) -> None:
        """Load a device from the available devices."""
        # TODO: add description from available devices
        dev = Device(name=name, library=library, adapter_name=adapter_name)
        self.devices.append(dev)

    def _cmd_property(self, device_name: str, prop: str, value: str = "") -> None:
        if device_name == Keyword.CoreDevice and prop == Keyword.CoreInitialize:
            try:
                self._initialized = bool(int(value))
            except (ValueError, TypeError):
                raise ValueError(f"Value {value!r} is not an integer") from None
            return

        dev = self.find_device(device_name)
        _prop = dev.set_default_prop(prop, value, pre_init=not self._initialized)
        _prop.value = value

    def _cmd_label(self, device_name: str, state: str, label: str) -> None:
        dev = self.find_device(device_name)
        if not isinstance(dev, StateDevice):
            self.devices[self.devices.index(dev)] = dev = StateDevice.from_device(dev)

        try:
            state_int = int(state)
        except (ValueError, TypeError):
            raise ValueError(f"State {state} is not an integer") from None
        dev.labels[state_int] = label

    def _cmd_config_group(
        self,
        group_name: str,
        preset_name: str,
        device_name: str,
        prop_name: str,
        value: str = "",
    ) -> None:
        cg = self.config_groups.setdefault(group_name, ConfigGroup(name=group_name))
        preset = cg.presets.setdefault(preset_name, ConfigPreset(name=preset_name))
        preset.settings.append(Setting(device_name, prop_name, value))

    def _cmd_pixel_size(
        self,
        preset_name: str,
        device_name: str,
        prop_name: str,
        value: str = "",
    ) -> None:
        # NOTE: this is quite similar to _cmd_config_group... maybe refactor?
        cg = self.pixel_size_group
        preset = cg.presets.setdefault(preset_name, PixelSizePreset(name=preset_name))
        preset.settings.append(Setting(device_name, prop_name, value))

    def _cmd_pixel_size_um(self, preset_name: str, value: str) -> None:
        try:
            preset = self.pixel_size_group.presets[preset_name]
        except KeyError:
            raise ValueError(f"Pixel size preset {preset_name!r} not found") from None

        try:
            preset.pixel_size_um = float(value)
        except ValueError as exc:
            raise ValueError(f"Invalid pixel size: {value}. Expected a float.") from exc

    def _cmd_pixel_size_affine(self, preset_name: str, *tform: float) -> None:
        try:
            preset = self.pixel_size_group.presets[preset_name]
        except KeyError:
            raise ValueError(f"Pixel size preset {preset_name!r} not found") from None

        # TODO: I think zero args is also a valid value for the affine transform
        if len(tform) != 6:
            raise ValueError(
                f"Expected 6 values for affine transform, got {len(tform)}"
            )

        try:
            preset.affine_transform = tuple(float(v) for v in tform)
        except ValueError as exc:
            raise ValueError(
                f"Invalid affine transform: {tform!r}. Expected 6 floats."
            ) from exc

    def _cmd_parent_id(self, device_name: str, parent_name: str) -> None:
        dev = self.find_device(device_name)
        dev.parent_name = parent_name

    def _cmd_delay(self, device_name: str, delay_ms: str) -> None:
        dev = self.find_device(device_name)
        try:
            dev.delay_ms = float(delay_ms)
        except ValueError as exc:
            raise ValueError(f"Invalid delay: {delay_ms!r}. Expected a float.") from exc

    def _cmd_focus_direction(self, device_name: str, direction: str) -> None:
        dev = self.find_device(device_name)
        if not isinstance(dev, StageDevice):
            self.devices[self.devices.index(dev)] = dev = StageDevice.from_device(dev)

        try:
            dev.focus_direction = FocusDirection(int(direction))
        except (ValueError, TypeError):
            raise ValueError(f"{direction} is not a valid FocusDirection") from None

    # Consider moving all of the to/from config file logic to a ConfigFile class
    _CMD_MAP: ClassVar[dict[CFGCommand, Callable[..., None]]] = {
        CFGCommand.Device: _cmd_device,
        CFGCommand.Property: _cmd_property,
        CFGCommand.Label: _cmd_label,
        CFGCommand.ConfigGroup: _cmd_config_group,
        CFGCommand.ConfigPixelSize: _cmd_pixel_size,
        CFGCommand.PixelSize_um: _cmd_pixel_size_um,
        CFGCommand.PixelSizeAffine: _cmd_pixel_size_affine,
        CFGCommand.ParentID: _cmd_parent_id,
        CFGCommand.FocusDirection: _cmd_focus_direction,
        CFGCommand.Delay: _cmd_delay,
    }


CFG_TEMPLATE = """# Generated by pymmcore-plus on {date}

# Reset
Property,Core,Initialize,0

# Devices
{devices}

# Pre-init settings for devices
{pre_init_settings}

# Pre-init settings for COM ports
{pre_init_com_settings}

# Hub (parent) references
{hub_refs}

# Initialize
Property,Core,Initialize,1

# Delays
{delays}

# Focus directions
{focus_directions}

# Roles
{roles}

# Camera-synchronized devices
{camera_synced_devices}

# Labels
{labels}

# Configuration presets
{config_presets}

# PixelSize settings
{pixel_size_settings}
"""
