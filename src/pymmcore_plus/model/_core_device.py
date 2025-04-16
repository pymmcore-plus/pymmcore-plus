from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pymmcore_plus import CMMCorePlus, DeviceType, Keyword

from ._device import Device
from ._property import Property

if TYPE_CHECKING:
    from collections.abc import Container

    from pymmcore_plus.model._core_link import ErrCallback

CORE = Keyword.CoreDevice.value


def _core_prop(name: str, val: str = "", allowed: tuple[str, ...] = ("",)) -> Property:
    return Property(
        CORE, str(name), value=val, is_read_only=False, allowed_values=allowed
    )


def _core_props() -> list[Property]:
    return [
        # _core_prop(Keyword.CoreInitialize, "0", ("0", "1")),
        _core_prop(Keyword.CoreAutoShutter, "1", ("0", "1")),
        _core_prop(Keyword.CoreCamera),
        _core_prop(Keyword.CoreShutter),
        _core_prop(Keyword.CoreFocus),
        _core_prop(Keyword.CoreXYStage),
        _core_prop(Keyword.CoreAutoFocus),
        _core_prop(Keyword.CoreImageProcessor),
        _core_prop(Keyword.CoreSLM),
        _core_prop(Keyword.CoreGalvo),
        _core_prop(Keyword.CoreChannelGroup),
        _core_prop(Keyword.CoreTimeoutMs),
    ]


@dataclass
class CoreDevice(Device):
    name: str = CORE
    adapter_name: str = CORE
    device_type: DeviceType = DeviceType.Core
    description: str = "Core device"
    properties: list[Property] = field(default_factory=_core_props)

    def __post_init__(self) -> None:
        self.CORE_GETTERS = {}

    def __setstate__(self, state: dict[str, Any]) -> None:
        super().__setstate__(state)
        prop_objects = []
        for prop in self.properties:
            if isinstance(prop, dict):
                prop = Property(**prop)
            prop_objects.append(prop)
        self.properties = prop_objects

    def __hash__(self) -> int:
        return super().__hash__()

    def apply_to_core(
        self,
        core: CMMCorePlus,
        *,
        exclude: Container[str] = (Keyword.CoreInitialize.value,),
        on_err: ErrCallback | None = None,
        apply_properties: bool = True,
        then_update: bool = True,
    ) -> None:
        # note: calling core.setProperty('Core', 'Initialize', '1') may cause a crash
        # if the core device is already initialized. However, it can't currently be
        # checked with core.getProperty('Core', 'Initialize') or
        # get.getDeviceInitializationStatus('Core').
        # see https://github.com/micro-manager/mmCoreAndDevices/issues/384
        for prop in self.properties:
            if prop.name not in exclude:
                core.setProperty(self.name, prop.name, prop.value)
        if then_update:
            self.update_from_core(core)
