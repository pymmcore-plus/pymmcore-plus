from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Container, Iterable

from pymmcore_plus import DeviceType, Keyword

from ._config_group import ConfigGroup
from ._core_device import CoreDevice
from ._device import Device, iter_available_devices
from ._pixel_size_config import PixelSizeGroup

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus

    from ._core_link import ErrCallback
    from ._property import Property


def _noop(*args: Any, **kwargs: Any) -> None:
    pass


@dataclass
class Microscope:
    """Full model of a microscope."""

    # XXX: Consider making a dedicated Core device
    # and disallowing the user from creating Device with type Core
    core_device: CoreDevice = field(default_factory=CoreDevice)
    devices: list[Device] = field(default_factory=list)
    config_groups: dict[str, ConfigGroup] = field(default_factory=dict)
    pixel_size_group: PixelSizeGroup = field(default_factory=PixelSizeGroup)
    config_file: str = ""

    initialized: bool = False
    available_devices: tuple[Device, ...] = field(default_factory=tuple, repr=False)

    def __post_init__(self) -> None:
        """Validate and initialized the Microscope."""
        # ensure core device exists:
        if any(d.device_type == DeviceType.Core for d in self.devices):
            raise ValueError(
                "Cannot have CoreDevice in devices list. "
                "Use core_device field to set the Core device."
            )

    def reset(self) -> None:
        """Reset the Microscope to an empty state."""
        defaults = Microscope()
        for f in fields(self):
            setattr(self, f.name, getattr(defaults, f.name))

    @property
    def assigned_com_ports(self) -> dict[Device, Device]:
        """Return map of SerialDevice -> DeviceUsingIt.

        A com port is "claimed" if it is assigned to a device.
        """
        assigned: dict[Device, Device] = {}
        com_devices = {d.name: d for d in self.available_serial_devices}
        for dev in self.devices:
            for prop in dev.properties:
                if prop.name == Keyword.Port and prop.value in com_devices:
                    assigned[com_devices[prop.value]] = dev
        return assigned

    @property
    def available_serial_devices(self) -> Iterable[Device]:
        """Return the available com ports."""
        for dev in self.available_devices:
            if dev.device_type == DeviceType.Serial:
                yield dev

    def get_device(self, name: str) -> Device:
        """Get a device by name."""
        for dev in self.devices:
            if dev.name == name:
                return dev
        raise KeyError(f"Device {name} not found")

    def filter_devices(
        self,
        name: str | None = None,
        library: str | None = None,
        adapter_name: str | None = None,
        description: str | None = None,
        device_type: DeviceType | None = None,
        parent_label: str | None = None,
    ) -> Iterable[Device]:
        """Filter devices by name ."""
        if isinstance(device_type, str):
            device_type = DeviceType[device_type]
        if name == Keyword.CoreDevice.value or device_type == DeviceType.Core:
            yield self.core_device
            return

        criteria = {
            k: val for k, val in locals().items() if k != "self" and val is not None
        }
        for dev in self.devices:
            if all(getattr(dev, attr) == value for attr, value in criteria.items()):
                yield dev

    # ------------- Config-file methods -------------

    @classmethod
    def create_from_config(cls, config_file: str) -> Microscope:
        obj = cls()
        obj.load_config(config_file)
        return obj

    def load_config(self, path_or_text: str | Path) -> None:
        """Load model from a micro-manager config file or string."""
        from ._config_file import load_from_string

        if os.path.isfile(path_or_text):
            path = Path(path_or_text).expanduser().resolve()
            text = path.read_text()
            self.config_file = str(path)
        else:
            text = str(path_or_text)

        load_from_string(text, self)

    def save(self, path: str | Path) -> None:
        """Save model as a micro-manager config file."""
        from ._config_file import dump

        with open(path, "w") as fh:
            dump(self, fh)

    # ------------- Core-interacting methods -------------

    @classmethod
    def create_from_core(
        cls, core: CMMCorePlus, *args: Any, **kwargs: Any
    ) -> Microscope:
        obj = cls(*args, **kwargs)
        obj.update_from_core(core)
        return obj

    def update_from_core(
        self,
        core: CMMCorePlus,
        *,
        exclude: Container[str] = (),
        on_err: ErrCallback | None = None,
    ) -> None:
        """Update this object's values from the core."""
        # update devices
        if "devices" not in exclude:
            self.devices = [
                Device.create_from_core(core, name=name)
                for name in core.getLoadedDevices()
                if name != Keyword.CoreDevice
            ]
        if "core_device" not in exclude:
            self.core_device.update_from_core(core)
        if "available_devices" not in exclude:
            self.load_available_devices(core)
        if "config_groups" not in exclude:
            self.update_config_groups_from_core(core)
        if "pixel_size_configs" not in exclude:
            self.update_pixel_sizes_from_core(core)

    def initialize(
        self,
        core: CMMCorePlus,
        on_fail: Callable[[Device | Property, BaseException], None | bool] = _noop,
    ) -> None:
        """Attempt to initialize all devices in the model.

        Simulates what MMCore does upon loading config file.
        """

        # apply pre-init props and initialize com ports
        # sort, putting SerialDevices first, then HubDevices, then others
        def _sort_key(d: Device) -> int:
            return {DeviceType.Serial: 0, DeviceType.Hub: 1}.get(d.device_type, 2)

        devs_to_init = sorted((*self.assigned_com_ports, *self.devices), key=_sort_key)

        for device in devs_to_init:
            if device.device_type == DeviceType.Core:
                continue
            try:
                device.initialize(core, reload=True, apply_pre_init=True)
            except Exception as e:
                if on_fail(device, e):
                    return

    def load_available_devices(self, core: CMMCorePlus) -> None:
        """Load the available device list."""
        self.available_devices = tuple(iter_available_devices(core))

    def update_config_groups_from_core(self, core: CMMCorePlus) -> None:
        """Load config groups from the core."""
        self.config_groups = ConfigGroup.all_config_groups(core)
        # self.config_groups.update(ConfigGroup.all_config_groups(core))

    def update_pixel_sizes_from_core(self, core: CMMCorePlus) -> None:
        """Load pixel size groups from the core."""
        self.pixel_size_group = PixelSizeGroup.create_from_core(core)
