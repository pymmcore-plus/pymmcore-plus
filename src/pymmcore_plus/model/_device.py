from __future__ import annotations

import dataclasses
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from pymmcore_plus import CMMCorePlus, DeviceType, FocusDirection, Keyword
from pymmcore_plus._util import no_stdout
from pymmcore_plus.core._constants import DeviceInitializationState

from ._core_link import CoreObject
from ._property import Property

if TYPE_CHECKING:
    from collections.abc import Container, Iterable
    from typing import Any, Callable

    from typing_extensions import (
        Self,  # py311
        TypeAlias,  # py310
    )

    from pymmcore_plus.metadata.schema import DeviceInfo

    from ._core_link import ErrCallback
    from ._microscope import Microscope

    PropVal: TypeAlias = bool | float | int | str
    DeviceGetter: TypeAlias = Callable[[CMMCorePlus, str], Any]
    DeviceSetter: TypeAlias = Callable[[CMMCorePlus, str, Any], None]


UNDEFINED = "UNDEFINED"
DEVICE_GETTERS: dict[str, DeviceGetter] = {
    "library": CMMCorePlus.getDeviceLibrary,
    "adapter_name": CMMCorePlus.getDeviceName,
    "description": CMMCorePlus.getDeviceDescription,
    "device_type": CMMCorePlus.getDeviceType,
    "delay_ms": CMMCorePlus.getDeviceDelayMs,
    "uses_delay": CMMCorePlus.usesDeviceDelay,
    "parent_label": CMMCorePlus.getParentLabel,
    "property_names": CMMCorePlus.getDevicePropertyNames,
    # "is_busy": CMMCorePlus.deviceBusy,  # Leave this out... it can crash when checking
}
STATE_DEVICE_GETTERS: dict[str, DeviceGetter] = {
    **DEVICE_GETTERS,
    "labels": CMMCorePlus.getStateLabels,
}
STAGE_DEVICE_GETTERS: dict[str, DeviceGetter] = {
    **DEVICE_GETTERS,
    "labels": CMMCorePlus.getFocusDirection,
}
HUB_DEVICE_GETTERS: dict[str, DeviceGetter] = {
    **DEVICE_GETTERS,
    "children": CMMCorePlus.getInstalledDevices,
}


@dataclass
class Device(CoreObject):
    """Model of a device."""

    name: str = UNDEFINED  # or label?
    library: str = ""
    adapter_name: str = ""  # or name?
    description: str = ""
    device_type: DeviceType = DeviceType.Any  # perhaps UnknownType?
    properties: list[Property] = field(default_factory=list)
    delay_ms: float = 0.0
    uses_delay: bool = False
    parent_label: str = ""

    # not something that can be get/set from core...
    # but useful state to track in a model
    initialized: bool = False

    # NOTE: I began by using device subclasses for these, but it becomes very difficult
    # when you need to "promote" a device to a different type. For example, if you are
    # loading a config file, and the only information you have is the device name, you
    # won't know what type of device it is until later. While you can theoretically
    # promote the class at that point, it gets very messy.  The following attributes
    # are used to store data specific to certain device types.

    # StateDevice only
    labels: tuple[str, ...] = field(default_factory=tuple)
    # StageDevice only
    focus_direction: FocusDirection = FocusDirection.Unknown
    # HubDevice only
    # These are adapter_name (NOT loaded device labels) of child devices
    # from the same library that can be loaded into this hub.
    children: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_metadata(cls, metadata: DeviceInfo) -> Self:
        return cls(
            name=metadata["label"],
            library=metadata["library"],
            adapter_name=metadata["name"],
            description=metadata["description"],
            device_type=DeviceType[metadata["type"]],
            parent_label=metadata.get("parent_label") or "",
            labels=tuple(metadata.get("labels", [])),
            focus_direction=FocusDirection[metadata.get("focus_direction", "Unknown")],
            children=tuple(metadata.get("child_names", [])),
        )

    def __post_init__(self) -> None:
        if self.name == Keyword.CoreDevice or self.device_type == DeviceType.Core:
            raise ValueError(
                "Cannot create a Device with type Core. Use CoreDevice instead"
            )

        # give Serial devices the same name as their adapter
        if self.name == UNDEFINED and self.device_type == DeviceType.Serial:
            self.name = self.adapter_name

    def __hash__(self) -> int:
        return id(self)

    def get_property(self, name: str) -> Property:
        """Get a device by name."""
        for prop in self.properties:
            if prop.name == name:
                return prop
        raise ValueError(f"Device {self.name!r} has no property {name!r}.")

    def set_property(self, prop_name: str, value: Any) -> None:
        self.get_property(prop_name).value = value

    def set_prop_default(
        self, prop_name: str, value: str = "", **kwargs: Any
    ) -> Property:
        """Works similar to `dict.set_default`. Add property if it doesn't exist."""
        try:
            prop = self.get_property(prop_name)
        except ValueError:
            prop = Property(self.name, str(prop_name), value, **kwargs)
            self.properties.append(prop)
        return prop

    @property
    def port(self) -> str | None:
        """Returns the value of the first property named "Port".

        Returns `None` if the device has no port property.
        """
        return next(
            (prop.value for prop in self.properties if prop.name == Keyword.Port),
            None,
        )

    @port.setter
    def port(self, port: str) -> None:
        """Set the value of the first property named "Port"."""
        for prop in self.properties:
            if prop.name == Keyword.Port:
                prop.value = port
                break
        else:
            raise ValueError(f"Device {self.name} has no port property.")

    def replace(self, **kwargs: Any) -> Device:
        return dataclasses.replace(self, **kwargs)

    # ------------- Core-interacting methods -------------
    @classmethod
    def create_from_core(cls, core: CMMCorePlus, *args: Any, **kwargs: Any) -> Device:
        if (
            kwargs.get("name", UNDEFINED) == Keyword.CoreDevice
            or kwargs.get("device_type") == DeviceType.Core
        ):
            from ._core_device import CoreDevice

            cls = CoreDevice
        obj = cls(*args, **kwargs)
        obj.update_from_core(core)
        return obj

    def _core_args(self) -> tuple[str]:
        """Args to pass to all CORE_GETTERS."""
        return (self.name,)

    def update_from_core(
        self,
        core: CMMCorePlus,
        *,
        exclude: Container[str] = (),
        on_err: ErrCallback | None = None,
    ) -> None:
        """Update device properties from the core."""
        # need to update device_type first, to determine which getters to use
        if self.name not in core.getLoadedDevices():
            raise RuntimeError(f"Device {self.name} is not loaded in the core.")

        self.device_type = core.getDeviceType(self.name)
        self._update_core_getters()

        super().update_from_core(core, exclude=exclude, on_err=on_err)
        self.properties = [
            Property.create_from_core(core, device_name=self.name, name=prop_name)
            for prop_name in core.getDevicePropertyNames(self.name)
        ]

    # pulled out for the sake of picklability
    def _update_core_getters(self) -> None:
        self.CORE_GETTERS = {
            DeviceType.StateDevice: STATE_DEVICE_GETTERS,
            DeviceType.StageDevice: STAGE_DEVICE_GETTERS,
            DeviceType.Hub: HUB_DEVICE_GETTERS,
        }.get(self.device_type, DEVICE_GETTERS)

    def __reduce__(self) -> str | tuple[Any, ...]:
        return self.__class__, (), asdict(self)

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
        self._update_core_getters()

    def load(self, core: CMMCorePlus, *, reload: bool = False) -> None:
        """Load device properties from the core."""
        if reload and self.name in core.getLoadedDevices():
            # could check whether:
            # core.getDeviceLibrary(self.name) == self.library
            # core.getDeviceName(self.name) == self.adapter_name
            core.unloadDevice(self.name)
        core.loadDevice(self.name, self.library, self.adapter_name)
        self.initialized = False

    def unload(self, core: CMMCorePlus) -> None:
        """Unload device from the core."""
        core.unloadDevice(self.name)

    def initialize(
        self,
        core: CMMCorePlus,
        *,
        apply_pre_init: bool = False,
        reload: bool = False,
        then_update: bool = True,
    ) -> None:
        """Initialize the device in core."""
        if reload:
            self.load(core, reload=reload)

        if apply_pre_init:
            # FIXME: Do we need to differentiate setup props?
            for prop in self.properties:
                if prop.is_pre_init:
                    prop.apply_to_core(core, then_update=False)

        core.initializeDevice(self.name)
        self.initialized = True
        self.apply_to_core(core, then_update=then_update)

    def apply_to_core(
        self,
        core: CMMCorePlus,
        *,
        exclude: Container[str] = ("delay_ms",),
        on_err: ErrCallback | None = None,
        apply_properties: bool = True,
        then_update: bool = True,
    ) -> None:
        try:
            if "delay_ms" not in exclude:
                core.setDeviceDelayMs(self.name, self.delay_ms)
            if "parent_label" not in exclude:
                core.setParentLabel(self.name, self.parent_label)
            if "labels" not in exclude and self.device_type == DeviceType.State:
                for state, label in enumerate(self.labels):
                    core.defineStateLabel(self.name, state, label)
            if (
                "focus_direction" not in exclude
                and self.device_type == DeviceType.Stage
            ):
                core.setFocusDirection(self.name, self.focus_direction)

            # XXX: should we do this as well as parent_label above?
            # if "children" not in exclude and self.device_type == DeviceType.Hub:
            #     for child in self.children:
            #         core.setParentLabel(child, self.name)

        except RuntimeError as e:
            if callable(on_err):
                on_err(self, "delay_ms", e)

        if apply_properties:
            for prop in self.properties:
                prop.apply_to_core(core, then_update=False)

        if then_update:
            self.update_from_core(core)

        # TODO: should we be applying properties here as well?

    # def wait(self, core: CMMCorePlus) -> None:
    #     """Wait for device to finish."""
    #     core.waitForDevice(self.name)

    # def detect(self, core: CMMCorePlus) -> None:
    #     """Detect device."""
    #     core.detectDevice(self.name)

    # def follow_core(self, core: CMMCorePlus) -> None:
    #     core.events.propertyChanged.connect(self._on_core_change)

    # def unfollow_core(self, core: CMMCorePlus) -> None:
    #     core.events.propertyChanged.disconnect(self._on_core_change)

    # def _on_core_change(self, dev: str, prop: str, new_val: str) -> None:
    #     if dev == self.name and prop == self.name:
    #         self.value = new_val

    # ------------- DeviceType specific methods -------------

    def _assert_is(self, dev_type: DeviceType) -> None:
        if self.device_type != dev_type:
            raise ValueError(f"Device {self.name} is not a {dev_type.name!r}.")

    def child_descriptions(self, core: CMMCorePlus) -> tuple[str, ...]:
        self._assert_is(DeviceType.Hub)
        return tuple(
            core.getInstalledDeviceDescription(self.name, child)
            for child in self.children
        )

    def loaded_peripherals(self, core: CMMCorePlus) -> tuple[str, ...]:
        """Return device labels of all loaded devices that belong to this hub.

        NOTE: unlike "available_peripherals", this returns device labels currently
        loaded into core. It does not check whether the devices are in the model.
        """
        self._assert_is(DeviceType.Hub)
        return tuple(core.getLoadedPeripheralDevices(self.name))

    def available_peripherals(self, model: Microscope) -> Iterable[AvailableDevice]:
        """Return all available devices that belong to this hub that aren't in model."""
        self._assert_is(DeviceType.Hub)

        # get all available devices that belong to this hub
        # and have not been loaded
        for dev in model.available_devices:
            if (
                # has a parent hub
                (hub := dev.library_hub)
                # that is this hub
                and hub.library == self.library
                and hub.adapter_name == self.adapter_name
                # and has not been loaded into the model
                and not any(
                    model.filter_devices(
                        library=dev.library,
                        adapter_name=dev.adapter_name,
                        parent_label=self.name,
                    )
                )
            ):
                yield dev

    def set_label(self, state: int | str, label: str) -> None:
        """Set the label for a state device."""
        self._assert_is(DeviceType.State)

        try:
            state = int(state)
        except (ValueError, TypeError):
            raise ValueError(f"State {state!r} is not an integer") from None

        lst = list(self.labels)
        current_length = len(self.labels)

        # Expand the list with new strings if needed
        if state >= current_length:
            lst.extend(f"State-{i}" for i in range(current_length, state + 1))
        lst[state] = label
        self.labels = tuple(lst)


@dataclass
class AvailableDevice(Device):
    """Model of an available device, with a possible hub parent."""

    library_hub: AvailableDevice | None = None

    def __hash__(self) -> int:
        return super().__hash__()


def get_available_devices(core: CMMCorePlus) -> list[AvailableDevice]:
    """Iterate over available devices."""
    available_devices: list[AvailableDevice] = []
    library_to_hub: dict[tuple[str, str], AvailableDevice] = {}
    for lib_name in core.getDeviceAdapterNames():
        with suppress(RuntimeError):
            for dev in iter_available_library_devices(core, lib_name):
                available_devices.append(dev)
                if dev.device_type == DeviceType.Hub:
                    library_to_hub[(lib_name, dev.adapter_name)] = dev

    # now associate devices with their hubs
    for d in available_devices:
        if d.device_type != DeviceType.Hub:
            d.library_hub = library_to_hub.get((d.library, d.adapter_name))

    # We also need to check for child devices of loaded hubs
    # which will not visible via `core.getAvailableDevices`, and will only be
    # visible after a hub device has been loaded.
    # HACK: this is a bit of a hack, but it's due to the (multiple) ways that
    # hub devices and child devices work in MMCore
    for hub in core.getLoadedDevicesOfType(DeviceType.Hub):
        lib_name = core.getDeviceLibrary(hub)
        hub_dev = library_to_hub.get((lib_name, hub))
        if (
            core.getDeviceInitializationState(hub)
            != DeviceInitializationState.InitializedSuccessfully
        ):
            continue
        for child in core.getInstalledDevices(hub):
            dev = AvailableDevice(
                library=lib_name, adapter_name=child, library_hub=hub_dev
            )
            available_devices.append(dev)

    return available_devices


def iter_available_library_devices(
    core: CMMCorePlus, library_name: str
) -> Iterable[AvailableDevice]:
    """Iterate over Devices in the given library."""
    with no_stdout():
        devs = core.getAvailableDevices(library_name)  # this could raise
    types = core.getAvailableDeviceTypes(library_name)
    descriptions = core.getAvailableDeviceDescriptions(library_name)
    for dev_name, dev_type, desc in zip(devs, types, descriptions):
        yield AvailableDevice(
            library=library_name,
            adapter_name=dev_name,
            description=desc,
            device_type=DeviceType(dev_type),
        )
