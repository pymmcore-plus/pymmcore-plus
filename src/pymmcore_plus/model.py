"""In-memory models of MMCore devices and settings.

The purpose of this module is to have a model of a microscope that is
disconnected from the core instance. It can be loaded from or applied to
a core instance, but it is an independent representation of the state of
the microscope.  This is useful for saving and loading microscope settings
and for constructing a config GUI without having to interact with and update
the core instance.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, Iterator, NamedTuple, TypeVar

from pymmcore_plus import (
    CFGGroup,
    DeviceType,
    FocusDirection,
    Keyword,
    PropertyType,
)

from ._util import no_stdout

if TYPE_CHECKING:
    import builtins
    from typing import Final

    from pymmcore import CMMCore
    from typing_extensions import Self

    from pymmcore_plus import CMMCorePlus

    D = TypeVar("D", bound="Device")

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

UNDEFINED: Final = "UNDEFINED"
DEFAULT_AFFINE: Final = (1, 0, 0, 0, 1, 0)
PIXEL_SIZE_GROUP: Final = "PixelSizeGroup"


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
            devs = core.getAvailableDevices(library_name)  # this could raise
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
            prop = PropertyItem(self.name, str(prop_name), value, **kwargs)
            self.properties.append(prop)
        return prop

    def pre_init_props(self) -> Iterator[PropertyItem]:
        """Return a list of pre-init properties."""
        yield from (p for p in self.properties if p.pre_init)

    def setup_props(self) -> Iterator[PropertyItem]:
        """Return a list of properties to be used in setup."""
        yield from (p for p in self.properties if p.use_in_setup)

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


@dataclass
class SerialDevice(Device):
    """Model of the core device."""

    type: DeviceType = DeviceType.Serial

    def __post_init__(self) -> None:
        """Validate the SerialDevice."""
        # can't put this as field default because of dataclass limitations
        if self.name == UNDEFINED:
            self.name = self.adapter_name


@dataclass
class CoreDevice(Device):
    """Model of the core device."""

    name: str = Keyword.CoreDevice.value
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


class Setting(NamedTuple):
    """Model of a device setting."""

    device_name: str = UNDEFINED
    property_name: str = UNDEFINED
    property_value: str = UNDEFINED


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


ConfigPresetType = TypeVar("ConfigPresetType", bound="ConfigPreset")


@dataclass
class ConfigGroup(Generic[ConfigPresetType]):
    """ConfigGroup model."""

    name: str
    presets: dict[str, ConfigPresetType] = field(default_factory=dict)


@dataclass
class PixelSizeGroup(ConfigGroup[PixelSizePreset]):
    """Model of the pixel size group."""

    name: str = PIXEL_SIZE_GROUP
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


@dataclass
class Microscope:
    """Full model of a microscope."""

    devices: list[Device] = field(default_factory=list)
    config_groups: dict[str, ConfigGroup] = field(default_factory=dict)
    # config_groups: dict[str, dict[str, list[tuple]]] = field(default_factory=dict)
    pixel_size_group: PixelSizeGroup = field(default_factory=PixelSizeGroup)
    available_devices: tuple[Device, ...] = field(default_factory=tuple)
    available_com_ports: tuple[Device, ...] = field(default_factory=tuple)
    assigned_com_ports: dict[str, Device] = field(default_factory=dict)
    bad_libraries: set[str] = field(default_factory=set)
    config_file: str = ""
    initialized: bool = False

    def __post_init__(self) -> None:
        """Validate and initialized the Microscope."""
        # Used during load_from_file to check whether the init step has been run

        # ensure core device exists:
        if not any(isinstance(d, CoreDevice) for d in self.devices):
            self.devices.append(CoreDevice())

        # ensure system configs:
        sys_cfgs: list[tuple[str, tuple[str, ...]]] = [
            (str(CFGGroup.System), (CFGGroup.System_Startup.value,)),
            (str(Keyword.Channel), ()),
        ]
        for cfg_grp, presets in sys_cfgs:
            cg = self.config_groups.setdefault(cfg_grp, ConfigGroup(name=cfg_grp))
            for preset in presets:
                cg.presets.setdefault(preset, ConfigPreset(name=preset))

    @property
    def core(self) -> CoreDevice:
        """Return the CoreDevice."""
        return next(d for d in self.devices if isinstance(d, CoreDevice))

    @property
    def hubs(self) -> tuple[HubDevice, ...]:
        """Return a tuple of HubDevices."""
        return tuple(d for d in self.available_devices if isinstance(d, HubDevice))

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
        self.bad_libraries.clear()
        devs: list[Device] = []
        com_ports: list[Device] = []

        for lib_name in core.getDeviceAdapterNames():
            # should we be excluding serial ports here? like MMStudio?
            try:
                contents = Device.library_contents(core, lib_name)
            except RuntimeError:
                self.bad_libraries.add(lib_name)
                continue

            for dev in contents:
                if dev.type == DeviceType.Serial:
                    com_ports.append(dev)
                else:
                    devs.append(dev)
        self.available_devices = tuple(devs)
        self.available_com_ports = tuple(com_ports)

    def load(self, path: str | Path) -> None:
        """Save model as a micro-manager config file."""
        path = Path(path).expanduser().resolve()
        self.load_from_string(path.read_text())
        self.config_file = str(path)

    def load_from_string(self, text: str) -> None:
        """Load the Microscope from a string."""
        from ._config import load_from_string

        load_from_string(text, self)

    def save(self, path: str | Path) -> None:
        """Save model as a micro-manager config file."""
        from ._config import dump

        with open(path, "w") as fh:
            dump(self, fh)
