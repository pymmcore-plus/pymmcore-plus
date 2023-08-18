from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pymmcore_plus import DeviceType, FocusDirection, PropertyType

if TYPE_CHECKING:
    import builtins

    from pymmcore import CMMCore
    from typing_extensions import Self


@dataclass
class PropertyItem:
    """Model of a device property."""

    device: str
    name: str
    value: str
    read_only: bool = False
    pre_init: bool = False
    allowed: tuple[str, ...] = field(default_factory=set)
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
            type=core.getPropertyType(device_name, property_name),
            device_type=core.getDeviceType(device_name),
        )


UNDEFINED = "UNDEFINED"


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
    parent: HubDevice | None = None
    initialized: bool = False

    @classmethod
    def create_from_core(
        cls, core: CMMCore, device_name: str, *, parent: HubDevice | None = None
    ) -> Device:
        """Create a Device populated with current core values."""
        type_ = core.getDeviceType(device_name)
        dev = cls._subcls(type_)(
            name=device_name,
            library=core.getDeviceLibrary(device_name),
            adapter_name=core.getDeviceName(device_name),
            description=core.getDeviceDescription(device_name),
            delay_ms=core.getDeviceDelayMs(device_name),
            parent=parent,
        )
        dev.update_from_core(core)  # let subclass update specific values
        return dev

    def update_from_core(self, core: CMMCore) -> None:
        """Update the Device with current core values."""
        self.properties = [
            PropertyItem.create_from_core(core, self.name, prop_name)
            for prop_name in core.getDevicePropertyNames(self.name)
        ]
        self.type = DeviceType(core.getDeviceType(self.name))
        self.uses_delay = core.usesDeviceDelay(self.name)

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

    labels: tuple[str, ...] = field(default_factory=tuple)
    type: DeviceType = DeviceType.State

    def update_from_core(self, core: CMMCore) -> None:
        """Update the StateDevice with current core values."""
        super().update_from_core(core)
        self.labels = core.getStateLabels(self.name)

    @property
    def num_states(self) -> int:
        """Return the number of states."""
        return len(self.labels)


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


@dataclass
class Microscope:
    """Full model of a microscope."""

    devices: list[Device] = field(default_factory=list)
    available_devices: tuple[Device, ...] = field(default_factory=tuple)

    config_file: str = ""

    def __post_init__(self) -> None:
        """Validate the Microscope."""
        if all(x.type != DeviceType.Core for x in self.devices):
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
        if not self.available_devices:
            self.update_available_devies(core)

    def update_available_devies(self, core: CMMCore) -> None:
        """Return a tuple of available Devices."""
        devs: list[Device] = []
        for lib_name in core.getDeviceAdapterNames():
            # should we be excluding serial ports here? like MMStudio?
            devs.extend(Device.library_contents(core, lib_name))
        self.available_devices = tuple(devs)

    @property
    def hub_devices(self) -> tuple[HubDevice, ...]:
        """Return a tuple of HubDevices."""
        return tuple(d for d in self.available_devices if isinstance(d, HubDevice))
