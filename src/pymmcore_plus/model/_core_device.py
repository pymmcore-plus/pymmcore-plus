from dataclasses import dataclass, field

from pymmcore_plus import DeviceType, Keyword

from ._device import Device
from ._property import Property

CORE = Keyword.CoreDevice.value


def _core_prop(name: str, val: str = "", allowed: tuple[str, ...] = ("",)) -> Property:
    return Property(
        CORE, str(name), value=val, is_read_only=False, allowed_values=allowed
    )


def _core_props() -> list[Property]:
    return [
        _core_prop(Keyword.CoreInitialize, "0", ("0", "1")),
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
        self.CORE_GETTERS = {}  # type: ignore
