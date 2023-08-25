from dataclasses import dataclass, field

from pymmcore_plus import DeviceType, Keyword

from ._device import Device
from ._property import Property


@dataclass
class CoreDevice(Device):
    name: str = Keyword.CoreDevice.value
    adapter_name: str = Keyword.CoreDevice.value
    device_type: DeviceType = DeviceType.Core
    description: str = f"{Keyword.CoreDevice.value} device"
    properties: list[Property] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.set_prop_default(Keyword.CoreCamera)
        self.set_prop_default(Keyword.CoreShutter)
        self.set_prop_default(Keyword.CoreFocus)
        self.set_prop_default(Keyword.CoreAutoShutter, "1")
