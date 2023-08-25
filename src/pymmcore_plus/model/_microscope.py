from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Container, Iterable

from pymmcore_plus import CFGGroup, DeviceType, Keyword

from ._config_group import ConfigGroup, ConfigPreset
from ._device import Device, iter_available_devices
from ._pixel_size_config import PixelSizeGroup

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus

    from ._core_link import ErrCallback


@dataclass
class Microscope:
    """Full model of a microscope."""

    # XXX: Consider making a dedicated Core device
    # and disallowing the user from creating Device with type Core
    devices: list[Device] = field(default_factory=list)
    config_groups: dict[str, ConfigGroup] = field(default_factory=dict)
    pixel_size_configs: PixelSizeGroup = field(default_factory=PixelSizeGroup)
    config_file: str = ""

    initialized: bool = False
    available_devices: tuple[Device, ...] = field(default_factory=tuple, repr=False)

    def __post_init__(self) -> None:
        """Validate and initialized the Microscope."""
        # ensure core device exists:
        for dev in self.devices:
            if dev.device_type == DeviceType.Core:
                core_dev = dev
                break
        else:
            core_dev = Device(
                name=Keyword.CoreDevice.value,
                adapter_name=Keyword.CoreDevice.value,
                device_type=DeviceType.Core,
                description=f"{Keyword.CoreDevice.value} device",
            )
            self.devices.append(core_dev)

        core_dev.set_prop_default(Keyword.CoreCamera)
        core_dev.set_prop_default(Keyword.CoreShutter)
        core_dev.set_prop_default(Keyword.CoreFocus)
        core_dev.set_prop_default(Keyword.CoreAutoShutter, "1")

        SYS_CONFIGS: list[tuple[str, tuple[str, ...]]] = [
            (CFGGroup.System.value, (CFGGroup.System_Startup.value,)),
            (Keyword.Channel.value, ()),
        ]

        # ensure system configs exist:
        for cfg_grp, presets in SYS_CONFIGS:
            cg = self.config_groups.setdefault(str(cfg_grp), ConfigGroup(name=cfg_grp))
            for preset in presets:
                cg.presets.setdefault(str(preset), ConfigPreset(name=preset))

    def reset(self) -> None:
        """Reset the Microscope to an empty state."""
        defaults = Microscope()
        for f in fields(self):
            setattr(self, f.name, getattr(defaults, f.name))

    @classmethod
    def create_from_config(cls, config_file: str) -> Microscope:
        obj = cls()
        obj.load_config(config_file)
        return obj

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
            ]
        if "available_devices" not in exclude:
            self.load_available_devices(core)
        if "config_groups" not in exclude:
            self.update_config_groups_from_core(core)
        if "pixel_size_configs" not in exclude:
            self.update_pixel_sizes_from_core(core)

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

    def load_available_devices(self, core: CMMCorePlus) -> None:
        """Load the available device list."""
        self.available_devices = tuple(iter_available_devices(core))

    def update_config_groups_from_core(self, core: CMMCorePlus) -> None:
        """Load config groups from the core."""
        self.config_groups = ConfigGroup.all_config_groups(core)

    def update_pixel_sizes_from_core(self, core: CMMCorePlus) -> None:
        """Load pixel size groups from the core."""
        self.pixel_size_configs = PixelSizeGroup.create_from_core(core)

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
        criteria = {
            k: val for k, val in locals().items() if k != "self" and val is not None
        }
        for dev in self.devices:
            if all(getattr(dev, attr) == value for attr, value in criteria.items()):
                yield dev

    def save(self, path: str | Path) -> None:
        """Save model as a micro-manager config file."""
        from ._config_file import dump

        with open(path, "w") as fh:
            dump(self, fh)
