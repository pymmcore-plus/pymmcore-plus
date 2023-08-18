from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pymmcore_plus import CFGCommand, DeviceType, FocusDirection, Keyword, PropertyType

if TYPE_CHECKING:
    import builtins

    from pymmcore import CMMCore
    from typing_extensions import Self

UNDEFINED = "UNDEFINED"


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
            raise ValueError("Device Type mismatch")
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

    def pre_init_props(self) -> list[PropertyItem]:
        """Return a list of pre-init properties."""
        return [p for p in self.properties if p.pre_init]

    def to_cfg(self) -> str:
        """Return a config string for this device."""
        return _cfg_field(CFGCommand.Device, self.name, self.library, self.adapter_name)


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
        return _cfg_field(
            CFGCommand.FocusDirection, self.name, self.focus_direction.value
        )


@dataclass
class StateDevice(Device):
    """Model of a state device."""

    labels: tuple[str, ...] = field(default_factory=tuple)
    type: DeviceType = DeviceType.State

    def update_from_core(self, core: CMMCore) -> None:
        """Update the StateDevice with current core values."""
        super().update_from_core(core)
        self.labels = core.getStateLabels(self.name)

    def labels_cfg(self) -> list[str]:
        """Return a list of config strings for this device's labels."""
        return [
            _cfg_field(CFGCommand.Label, self.name, state, label)
            for state, label in enumerate(self.labels)
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

    type: DeviceType = DeviceType.Core
    description = "Core device"

    def roles(self) -> list[str]:
        """Return the roles of this device."""
        return [
            _prop_field(Keyword.CoreDevice, field, prop.value)
            for field in (
                Keyword.CoreCamera,
                Keyword.CoreShutter,
                Keyword.CoreFocus,
                Keyword.CoreAutoShutter,
            )
            if (prop := self.find_property(field))
        ]


@dataclass
class ConfigGroup:
    ...


@dataclass
class Microscope:
    """Full model of a microscope."""

    devices: list[Device] = field(default_factory=list)
    config_groups: dict[str, ConfigGroup] = field(default_factory=dict)
    available_devices: tuple[Device, ...] = field(default_factory=tuple)
    available_com_ports: tuple[Device, ...] = field(default_factory=tuple)
    assigned_com_ports: dict[str, Device] = field(default_factory=dict)
    config_file: str = ""

    def __post_init__(self) -> None:
        """Validate the Microscope."""
        if not any(isinstance(x, CoreDevice) for x in self.devices):
            self.devices.append(
                CoreDevice(name="Core", library="", adapter_name="MMCore")
            )

    @classmethod
    def create_from_core(cls, core: CMMCore) -> Microscope:
        """Create a Microscope populated with current core values."""
        obj = cls(
            devices=[
                Device.create_from_core(core, device_name)
                for device_name in core.getLoadedDevices()
            ]
        )
        obj.update_available_devies(core)
        return obj

    def update_from_core(self, core: CMMCore) -> None:
        """Update the Microscope with current core values."""
        for device in self.devices:
            device.update_from_core(core)
        self.update_available_devies(core)

    def load_core_configs(self, core: CMMCore) -> None:
        self.config_groups.clear()
        for group_name in core.getAvailableConfigGroups():
            self.config_groups[group_name] = ConfigGroup(
                name=group_name,
                config_names=core.getAvailableConfigs(group_name),
                current_config=core.getCurrentConfig(group_name),
            )

    def update_available_devies(self, core: CMMCore) -> None:
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

    def save(self, path: str) -> None:
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
            pre_init_settings.extend(p.to_cfg() for p in d.properties if p.pre_init)
            if d.parent_name:
                hub_refs.append(_cfg_field(CFGCommand.ParentID, d.name, d.parent_name))
            if d.delay_ms:
                delays.append(_cfg_field(CFGCommand.Delay, d.name, d.delay_ms))
            if isinstance(d, StageDevice):
                focus_directions.append(d.focus_cfg())
            if isinstance(d, StateDevice):
                if d.labels:
                    labels.append(f"# {d.name}")
                    # NOTE: MMStudio reverses the order
                    labels.extend(d.labels_cfg())

        return CFG_TEMPLATE.format(
            date=date,
            devices="\n".join(devices),
            pre_init_settings="\n".join(pre_init_settings),
            pre_init_com_settings="\n",
            hub_refs="\n".join(hub_refs),
            delays="\n".join(delays),
            focus_directions="\n".join(focus_directions),
            roles="\n".join(self.core.roles()),
            camera_synced_devices="",
            labels="\n".join(labels),
            config_presets="",
            pixel_size_settings="",
        )


CFG_TEMPLATE = """
# Generated by pymmcore-plus on {date}

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
