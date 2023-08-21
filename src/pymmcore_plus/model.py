"""In-memory models of MMCore devices and settings.

The purpose of this module is to have a model of a microscope that is
disconnected from the core instance. It can be loaded from or applied to
a core instance, but it is an independent representation of the state of
the microscope.  This is useful for saving and loading microscope settings
and for constructing a config GUI without having to interact with and update
the core instance.
"""
from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import InitVar, dataclass, field, fields
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Container,
    Generic,
    Iterable,
    Iterator,
    NamedTuple,
    TypeVar,
)

from pymmcore_plus import (
    CFGGroup,
    CMMCorePlus,
    DeviceType,
    FocusDirection,
    Keyword,
    PropertyType,
)

from ._util import no_stdout

if TYPE_CHECKING:
    from typing import Final

    D = TypeVar("D", bound="Device")

__all__ = ["ConfigGroup", "ConfigPreset", "Device", "Microscope", "Property", "Setting"]

logger = logging.getLogger(__name__)
UNDEFINED: Final = "UNDEFINED"
DEFAULT_AFFINE: Final = (1, 0, 0, 0, 1, 0)
PIXEL_SIZE_GROUP: Final = "PixelSizeGroup"
PROP_GETTERS: Final[dict[str, Callable[[CMMCorePlus, str, str], Any]]] = {
    "value": CMMCorePlus.getProperty,
    "read_only": CMMCorePlus.isPropertyReadOnly,
    "pre_init": CMMCorePlus.isPropertyPreInit,
    "allowed": CMMCorePlus.getAllowedPropertyValues,
    "has_limits": CMMCorePlus.hasPropertyLimits,
    "lower_limit": CMMCorePlus.getPropertyLowerLimit,
    "upper_limit": CMMCorePlus.getPropertyUpperLimit,
    "property_type": CMMCorePlus.getPropertyType,
}
DEVICE_GETTERS: Final[dict[str, Callable[[CMMCorePlus, str], Any]]] = {
    "is_busy": CMMCorePlus.deviceBusy,
    "delay_ms": CMMCorePlus.getDeviceDelayMs,
    "uses_delay": CMMCorePlus.usesDeviceDelay,
    "description": CMMCorePlus.getDeviceDescription,
    "library": CMMCorePlus.getDeviceLibrary,
    "adapter_name": CMMCorePlus.getDeviceName,
    "property_names": CMMCorePlus.getDevicePropertyNames,
    "device_type": CMMCorePlus.getDeviceType,
}
SYS_CONFIGS: list[tuple[str, tuple[str, ...]]] = [
    (CFGGroup.System.value, (CFGGroup.System_Startup.value,)),
    (Keyword.Channel.value, ()),
]


def _noop(*_: Any, **__: Any) -> None:
    pass


def _ensure_core(core: CMMCorePlus | None) -> CMMCorePlus:
    if isinstance(core, CMMCorePlus):
        return core
    # TODO: give better error message with name/signature of caller
    raise TypeError(
        "No core is associated with this object, you must pass a core instance"
    )


@dataclass
class CoreLinked:
    """Class that may have a connection to a core object."""

    from_core: InitVar[CMMCorePlus | None] = field(default=None, kw_only=True)

    def __post_init__(self, from_core: CMMCorePlus | None) -> None:
        """Post-init hook to fetch values from the core, if available."""
        self._core: CMMCorePlus | None = from_core
        if isinstance(from_core, CMMCorePlus):
            self.update_from_core()

    @property
    def core(self) -> CMMCorePlus | None:
        """A core instance associated with this object, if any.

        This core will be used to fetch/update values from/to the core.
        """
        return self._core

    def update_from_core(
        self, core: CMMCorePlus | None = None, *, exclude: Container[str] = ()
    ) -> None:
        """Update this object's values from the core."""
        return


@dataclass
class Property(CoreLinked):
    """Model of a device property."""

    device_name: str
    name: str
    value: str = ""
    read_only: bool = False
    pre_init: bool = False
    allowed: tuple[str, ...] = field(default_factory=tuple)
    has_limits: bool = False
    lower_limit: float = 0.0
    upper_limit: float = 0.0
    property_type: PropertyType = PropertyType.Undef
    device_type: DeviceType = DeviceType.Unknown
    use_in_setup: bool = False  # setupProperties_

    def update_from_core(
        self, core: CMMCorePlus | None = None, *, exclude: Container[str] = ()
    ) -> None:
        """Fetch the current value of this property from the core."""
        core = _ensure_core(core or self.core)
        try:
            self.device_type = core.getDeviceType(self.device_name)
        except RuntimeError as e:
            logger.warning(f"Cannot update property {self.name} from core: {e}")
            return

        field_names = {f.name for f in fields(self)}
        for field_name, getter in PROP_GETTERS.items():
            if field_name in field_names:
                with suppress(RuntimeError):
                    val = getter(core, self.device_name, self.name)
                    setattr(self, field_name, val)

    def apply_to_core(self, core: CMMCorePlus | None = None) -> None:
        """Apply this object's values to the core."""
        core = _ensure_core(core or self.core)
        core.setProperty(self.device_name, self.name, self.value)


@dataclass
class Device(CoreLinked):
    """Model of a device."""

    name: str = UNDEFINED
    library: str = ""
    adapter_name: str = ""
    description: str = ""
    device_type: DeviceType = DeviceType.Any  # perhaps UnknownType?
    properties: list[Property] = field(default_factory=list)
    delay_ms: float = 0.0
    uses_delay: bool = False
    parent_name: str = ""
    initialized: bool = False

    # NOTE: I began by using device subclasses for these, but it becomes very difficult
    # when you need to "promote" a device to a different type. For example, if you are
    # loading a config file, and the only information you have is the device name, you
    # won't know what type of device it is until later. While you can theoretically
    # promote the class at that point, it gets very messy.  The following attributes
    # are used to store data specific to certain device types.

    # StateDevice only
    labels: dict[int, str] = field(default_factory=dict)

    # StageDevice only
    focus_direction: FocusDirection = FocusDirection.Unknown

    # HubDevice only
    children: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self, from_core: CMMCorePlus | None) -> None:
        """Change UNDEFINED serial device names."""
        super().__post_init__(from_core)

        # give serial devives their adapter name
        if self.name == UNDEFINED and self.device_type != DeviceType.Serial:
            self.name = self.adapter_name

    def update_from_core(
        self,
        core: CMMCorePlus | None = None,
        *,
        exclude: Container[str] = ("delay_ms",),
        update_properties: bool = True,
        remove_stale_properties: bool = True,
    ) -> None:
        """Fetch the current value of this property from the core."""
        # NOTE: from MMStudio: do not load the delay value from the hardware
        # we will always use settings defined in the config file
        # self.delay_ms = core.getDeviceDelayMs(self.name)
        core = _ensure_core(core or self.core)
        if self.name not in core.getLoadedDevices():
            return

        # update device fields
        field_names = {f.name for f in fields(self)}
        for field_name, getter in DEVICE_GETTERS.items():
            if field_name in field_names and field_name not in exclude:
                with suppress(RuntimeError):
                    val = getter(core, self.name)
                    setattr(self, field_name, val)

        # update properties
        if update_properties:
            prop_names: set[str] = set()
            core_names = core.getDevicePropertyNames(self.name)

            # update existing properties
            for prop in list(self.properties):
                prop_names.add(prop.name)
                prop.update_from_core(core, exclude=exclude)

                # remove stale properties
                if remove_stale_properties and prop.name not in core_names:
                    self.properties.remove(prop)

            # add new ones
            for name in core_names:
                if name not in prop_names:
                    self.properties.append(
                        Property(device_name=self.name, name=name, from_core=core)
                    )

        # handle device-type specific stuff
        if self.device_type == DeviceType.State:
            with suppress(RuntimeError):
                # may fail if not initialized, etc...
                self.labels = dict(enumerate(core.getStateLabels(self.name)))

        if self.device_type == DeviceType.Stage:
            with suppress(RuntimeError):
                self.focus_direction = FocusDirection(core.getFocusDirection(self.name))

        if self.device_type == DeviceType.Hub:
            if self.initialized and not self.children:
                with suppress(RuntimeError):
                    self.children = tuple(core.getInstalledDevices(self.name))

    @property
    def port(self) -> str:
        """Return the port of the device, if it has one."""
        return next(
            (prop.value for prop in self.properties if prop.name == Keyword.Port),
            "",
        )

    def rename_in_core(self, new_name: str, core: CMMCorePlus | None = None) -> None:
        """Unload the device, rename it, and reload it in core."""
        core = _ensure_core(core or self.core)
        with suppress(RuntimeError):
            core.unloadDevice(self.name)
        self.initialized = False
        core.loadDevice(new_name, self.library, self.adapter_name)
        self.name = new_name
        core.setParentLabel(new_name, self.parent_name)

    def load_in_core(
        self, core: CMMCorePlus | None = None, reload: bool = False
    ) -> None:
        """Load the device in core."""
        core = _ensure_core(core or self.core)
        if reload:
            with suppress(RuntimeError):
                core.unloadDevice(self.name)
            self.initialized = False
        core.loadDevice(self.name, self.library, self.adapter_name)

    def initialize_in_core(self, core: CMMCorePlus | None = None) -> None:
        """Initialize the device in core."""
        _ensure_core(core or self.core).initializeDevice(self.name)
        self.initialized = True

    @staticmethod
    def library_contents(core: CMMCorePlus, library_name: str) -> tuple[Device, ...]:
        """Return a tuple of Devices in the given library."""
        with no_stdout():
            devs = core.getAvailableDevices(library_name)  # this could raise
        types = core.getAvailableDeviceTypes(library_name)
        descriptions = core.getAvailableDeviceDescriptions(library_name)
        return tuple(
            Device(
                library=library_name,
                adapter_name=dev_name,
                description=desc,
                device_type=DeviceType(dev_type),
            )
            for dev_name, dev_type, desc in zip(devs, types, descriptions)
        )

    def find_property(self, prop_name: str) -> Property | None:
        """Find a property by name."""
        return next((p for p in self.properties if p.name == prop_name), None)

    def set_prop_default(
        self, prop_name: str, value: str = "", **kwargs: Any
    ) -> Property:
        """Works similar to `dict.set_default`. Add property if it doesn't exist."""
        if not (prop := self.find_property(prop_name)):
            prop = Property(self.name, str(prop_name), value, **kwargs)
            # set core?
            self.properties.append(prop)
        return prop

    def pre_init_props(self) -> Iterator[Property]:
        """Return a list of pre-init properties."""
        yield from (p for p in self.properties if p.pre_init)

    def setup_props(self) -> Iterator[Property]:
        """Return a list of properties to be used in setup."""
        yield from (p for p in self.properties if p.use_in_setup)

    def __rich_repr__(self) -> Iterable[tuple[str, Any]]:
        """Make AvailableDevices look a little less verbose."""
        if self.name == UNDEFINED:
            yield ("library", self.library)
            yield ("adapter_name", self.adapter_name)
            yield ("description", self.description)
            yield ("device_type", self.device_type.name)
        else:
            for _field in fields(self):
                yield (_field.name, getattr(self, _field.name))


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
class Microscope(CoreLinked):
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

    def __post_init__(self, from_core: CMMCorePlus | None) -> None:
        """Validate and initialized the Microscope."""
        if from_core is None and self.config_file and Path(self.config_file).is_file():
            self.load(self.config_file)

        # ensure core device exists:
        for dev in self.devices:
            if dev.device_type == DeviceType.Core:
                core_dev = dev
        else:
            core_dev = Device(
                name=Keyword.CoreDevice.value,
                adapter_name=Keyword.CoreDevice.value,
                device_type=DeviceType.Core,
                description=f"{Keyword.CoreDevice.value} device",
            )
            self.devices.append(core_dev)
        core_dev.set_prop_default(Keyword.CoreCamera, use_in_setup=True)
        core_dev.set_prop_default(Keyword.CoreShutter, use_in_setup=True)
        core_dev.set_prop_default(Keyword.CoreFocus, use_in_setup=True)
        core_dev.set_prop_default(Keyword.CoreAutoShutter, "1", use_in_setup=True)

        # ensure system configs exist:
        for cfg_grp, presets in SYS_CONFIGS:
            cg = self.config_groups.setdefault(str(cfg_grp), ConfigGroup(name=cfg_grp))
            for preset in presets:
                cg.presets.setdefault(str(preset), ConfigPreset(name=preset))

        super().__post_init__(from_core)

    def update_from_core(
        self,
        core: CMMCorePlus | None = None,
        *,
        exclude: Container[str] = ("delay_ms",),
        update_devices: bool = True,
        remove_stale_devices: bool = True,
        update_properties: bool = True,
        remove_stale_properties: bool = True,
    ) -> None:
        """Update this object's values from the core."""
        core = _ensure_core(core or self.core)
        # update devices
        if update_devices:
            our_device_names: set[str] = set()
            core_devices = core.getLoadedDevices()
            # update existing devices
            for dev in list(self.devices):
                our_device_names.add(dev.name)
                dev.update_from_core(
                    core,
                    exclude=exclude,
                    update_properties=update_properties,
                    remove_stale_properties=remove_stale_properties,
                )
                # remove stale devices
                if remove_stale_devices and dev.name not in core_devices:
                    self.devices.remove(dev)

            # add new devices
            for name in core_devices:
                if name not in our_device_names:
                    self.devices.append(Device(name, from_core=core))

        self.load_available_device_list(core)
        self.load_configs_from_core(core)
        self.load_pixel_sizes_from_core(core)

    @property
    def core_device(self) -> Device:
        """Return the CoreDevice."""
        return next(d for d in self.devices if d.device_type == DeviceType.Core)

    @property
    def hub_devices(self) -> tuple[Device, ...]:
        """Return a tuple of HubDevices."""
        return tuple(
            d for d in self.available_devices if d.device_type == DeviceType.Hub
        )

    def reset(self) -> None:
        """Reset the Microscope to an empty state."""
        defaults = Microscope()
        for f in fields(self):
            setattr(self, f.name, getattr(defaults, f.name))

    def has_device_name(self, device_name: str) -> bool:
        """Return True if the device is defined."""
        return any(d.name == device_name for d in self.devices)

    def has_adapter_name(self, library: str, hub_name: str, adapter_name: str) -> bool:
        """Return True if the adapter is defined."""
        return any(
            dev.adapter_name == adapter_name
            and dev.library == library
            and dev.parent_name == hub_name
            for dev in self.devices
        )

    def find_device(self, device_name: str | Device) -> Device:
        """Find a device by name or raise ValueError."""
        for d in self.devices:
            if d.name == device_name or d is device_name:
                return d
        raise ValueError(f"Device {device_name!r} not defined")

    def initialize_model(
        self,
        core: CMMCorePlus,
        on_fail: Callable[[Device | Property, BaseException], None] = _noop,
    ) -> None:
        """Attempt to initialize all devices in the model.

        Simulates what MMCore does upon loading config file.
        """
        # apply pre-init props and initialize com ports
        for device in self.assigned_com_ports.values():
            try:
                for prop in device.properties:
                    if prop.pre_init:
                        core.setProperty(device.name, prop.name, prop.value)
                core.initializeDevice(device.name)
                device.update_from_core(core)
            except Exception as e:
                on_fail(device, e)

        # apply pre-init properties
        for dev in self.devices:
            for prop in dev.setup_props():
                if prop.pre_init:
                    try:
                        core.setProperty(dev.name, prop.name, prop.value)
                    except Exception as e:
                        on_fail(prop, e)

        # initialize hubs first
        for d in sorted(self.devices, key=lambda d: d.device_type != DeviceType.Hub):
            if d.initialized or d.device_type == DeviceType.Core:
                continue
            if d.parent_name:
                core.setParentLabel(d.name, d.parent_name)
            try:
                core.initializeDevice(d.name)

                if d.device_type == DeviceType.State:
                    for state, label in d.labels.items():
                        core.defineStateLabel(d.name, state, label)

                d.update_from_core(core)
                d.initialized = True
            except Exception as e:
                on_fail(d, e)

    def load_model(self, core: CMMCorePlus) -> None:
        """Apply the model to the core instance."""
        # load all com ports
        for port_dev in self.available_com_ports:
            port_dev.load_in_core(core)

        # load devices
        for dev in self.devices:
            if dev.device_type != DeviceType.Core:
                dev.load_in_core(core)
                core.setParentLabel(dev.name, dev.parent_name)

        # find if any of the ports are being used
        for dev in self.devices:
            for prop in dev.properties:
                for port_dev in self.available_com_ports:
                    if prop.value == port_dev.name:
                        self.assigned_com_ports[port_dev.name] = port_dev

        for dev in (*self.devices, *self.available_com_ports):
            dev.update_from_core(core)

        self._remove_duplicate_ports()

    def _remove_duplicate_ports(self) -> None:
        # remove devices with names corresponding to available com ports
        avail = list(self.available_com_ports)
        for i, port_dev in enumerate(avail):
            try:
                dev = self.find_device(port_dev.name)
            except ValueError:
                continue
            else:
                avail[i] = dev
                self.remove_device(dev)
        self.available_com_ports = tuple(avail)

        # remove differently named com ports from device lists
        for dev in list(self.devices):
            if dev.device_type == DeviceType.SerialDevice:
                self.remove_device(dev)

    def remove_device(self, device: Device | str) -> None:
        """Remove a device from the model."""
        try:
            device = self.find_device(device)
        except ValueError:
            return  # device not found

        self.devices.remove(device)
        if device.port and all(dev.port != device.port for dev in self.devices):
            self.assigned_com_ports.pop(device.port, None)

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

    def load_available_device_list(self, core: CMMCorePlus) -> None:
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
                if dev.device_type == DeviceType.Serial:
                    com_ports.append(dev)
                else:
                    devs.append(dev)
        self.available_devices = tuple(devs)
        self.available_com_ports = tuple(com_ports)

    def load(self, path: str | Path) -> None:
        """Load model from a micro-manager config file."""
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
