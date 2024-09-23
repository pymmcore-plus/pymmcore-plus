from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from pymmcore_plus import DeviceType, Keyword

from ._config_group import ConfigGroup
from ._core_device import CoreDevice
from ._device import AvailableDevice, Device, get_available_devices
from ._pixel_size_config import PixelSizeGroup

if TYPE_CHECKING:
    from collections.abc import Container, Iterable

    from pymmcore_plus import CMMCorePlus
    from pymmcore_plus.metadata.schema import SummaryMetaV1

    from ._core_link import ErrCallback
    from ._property import Property


def _noop(*args: Any, **kwargs: Any) -> None:
    pass  # pragma: no cover


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

    @property
    def available_devices(self) -> tuple[AvailableDevice, ...]:
        return self._available_devices

    def __post_init__(self) -> None:
        """Validate and initialized the Microscope."""
        # ensure core device exists:
        if any(d.device_type == DeviceType.Core for d in self.devices):
            raise ValueError(
                "Cannot have CoreDevice in devices list. "
                "Use core_device field to set the Core device."
            )

        self._available_devices: tuple[AvailableDevice, ...] = ()
        self._compare_state: Microscope | None = None  # for is_dirty()

    def reset(self) -> None:
        """Reset the Microscope to an empty state."""
        defaults = Microscope()
        for f in fields(self):
            if f.name not in ("available_devices", "config_file"):
                setattr(self, f.name, getattr(defaults, f.name))

    def is_dirty(self) -> bool:
        """Return True if the model has changed since last save."""
        return self != (self._compare_state or Microscope())

    def mark_clean(self) -> None:
        """Mark the model as clean."""
        self._compare_state = deepcopy(self)

    @property
    def assigned_com_ports(self) -> dict[Device, Device]:
        """Return map of SerialDevice -> DeviceUsingIt.

        A com port is "claimed" if it is assigned to a device.
        """
        assigned: dict[Device, Device] = {}
        com_devices = {d.name: d for d in self.available_serial_devices}
        for dev in self.devices:
            # NOTE: one consequence if this structure is that devices
            # later in the list will "claim" the port of devices earlier in the list
            # in the case of a conflict.
            if dev.port in com_devices:
                assigned[com_devices[dev.port]] = dev

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
        raise KeyError(f"Device {name!r} not found")  # pragma: no cover

    def filter_devices(
        self,
        name: str | None = None,
        library: str | None = None,
        adapter_name: str | None = None,
        description: str | None = None,
        device_type: DeviceType | str | None = None,
        parent_label: str | None = None,
    ) -> Iterable[Device]:
        """Filter devices by name ."""
        if isinstance(device_type, str):
            device_type = DeviceType[device_type]
        if name == Keyword.CoreDevice.value or device_type == DeviceType.Core:
            yield self.core_device
            return  # pragma: no cover

        criteria = {
            k: val for k, val in locals().items() if k != "self" and val is not None
        }
        for dev in self.devices:
            if all(getattr(dev, attr) == value for attr, value in criteria.items()):
                yield dev

    # ------------- Config-file methods -------------

    @classmethod
    def create_from_config(cls, config_file: str | Path) -> Microscope:
        obj = cls()
        obj.load_config(config_file)
        obj.mark_clean()
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

        self.mark_clean()

    @classmethod
    def from_summary_metadata(cls, summary_meta: SummaryMetaV1) -> Microscope:
        """Create a Microscope model from summary metadata.

        This may be used to load a model from summary metadata, such as as written
        during the course of a Multi-Dimensional Acquisition.  This is useful for
        restoring the state of a microscope from a specific experiment, or writing
        out a cfg file that can be used to restore the state of the microscope.
        """
        core_device = next(
            (d for d in summary_meta["devices"] if d["name"] == Keyword.CoreDevice),
            None,
        )
        if core_device is None:
            raise ValueError("CoreDevice not found in metadata")
        return cls(
            core_device=CoreDevice.from_metadata(core_device),
            devices=[
                Device.from_metadata(d)
                for d in summary_meta["devices"]
                if d["name"] != Keyword.CoreDevice
            ],
            config_groups={
                grp["name"]: ConfigGroup.from_metadata(grp)
                for grp in summary_meta["config_groups"]
            },
            pixel_size_group=PixelSizeGroup.from_metadata(
                summary_meta["pixel_size_configs"]
            ),
            config_file=summary_meta["system_info"].get("system_configuration_file")
            or "",
        )

    # ------------- Core-interacting methods -------------

    @classmethod
    def create_from_core(
        cls, core: CMMCorePlus, *args: Any, **kwargs: Any
    ) -> Microscope:
        obj = cls(*args, **kwargs)
        obj.update_from_core(core)
        obj.mark_clean()
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
                if name != Keyword.CoreDevice  # type: ignore [comparison-overlap]
            ]
        if "core_device" not in exclude:
            self.core_device.update_from_core(core)
        if "available_devices" not in exclude:
            self.load_available_devices(core)
        if "config_groups" not in exclude:
            self.update_config_groups_from_core(core)
        if "pixel_size_configs" not in exclude:
            self.update_pixel_sizes_from_core(core)

    def apply_to_core(
        self,
        core: CMMCorePlus,
        *,
        exclude: Container[str] = (),
        on_err: ErrCallback | None = None,
        apply_properties: bool = True,
        then_update: bool = True,
    ) -> None:
        # this is a workaround for an inconsistency in MMCore itself
        # https://github.com/micro-manager/mmCoreAndDevices/issues/384
        init_prop = self.core_device.get_property(Keyword.CoreInitialize)
        core.setProperty(self.core_device.name, Keyword.CoreInitialize, init_prop.value)

        # devices must be initialized first
        if "devices" not in exclude:
            for device in self.devices:
                device.initialize(
                    core, reload=True, apply_pre_init=True, then_update=False
                )
        if "config_groups" not in exclude:
            for group in self.config_groups.values():
                group.apply_to_core(core, then_update=False)

        if "pixel_size_group" not in exclude:
            self.pixel_size_group.apply_to_core(core, then_update=False)
        # core device must come after config groups
        if "core_device" not in exclude:
            self.core_device.apply_to_core(
                core,
                on_err=on_err,
                apply_properties=apply_properties,
                then_update=False,
            )
        # apply_to_core must come after core
        if "devices" not in exclude:
            for device in self.devices:
                device.apply_to_core(
                    core,
                    on_err=on_err,
                    apply_properties=apply_properties,
                    then_update=then_update,
                )

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
            # shouldn't happen
            if device.device_type == DeviceType.Core:
                continue  # pragma: no cover
            try:
                device.initialize(core, reload=True, apply_pre_init=True)
            except Exception as e:
                if on_fail(device, e):
                    return

    def load_available_devices(self, core: CMMCorePlus) -> None:
        """Load the available device list."""
        self._available_devices = tuple(get_available_devices(core))

    def update_config_groups_from_core(self, core: CMMCorePlus) -> None:
        """Load config groups from the core."""
        self.config_groups = ConfigGroup.all_config_groups(core)
        # self.config_groups.update(ConfigGroup.all_config_groups(core))

    def update_pixel_sizes_from_core(self, core: CMMCorePlus) -> None:
        """Load pixel size groups from the core."""
        self.pixel_size_group = PixelSizeGroup.create_from_core(core)
