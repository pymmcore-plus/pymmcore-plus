from collections.abc import Iterator, KeysView
from typing import Literal, overload

from pymmcore_plus.core import DeviceType

from ._device import Device
from ._stage import StageDevice, _BaseStage
from ._xy_stage_device import XYStageDevice


class PyDeviceManager:
    """Manages loaded Python devices."""

    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}

    def load_device(self, label: str, device: Device) -> None:
        if label in self._devices:
            raise ValueError(f"The specified device label {label!r} is already in use")
        # TODO other stuff
        self._devices[label] = device

    def unload_device(self, device: str | Device) -> None:
        if isinstance(device, Device):
            label = next(k for k, v in self._devices.items() if v is device)
        else:
            label = device
        self._devices.pop(label, None)  # TODO ... check existence

    def unload_all_devices(self) -> None:
        self._devices.clear()  # TODO ...

    def keys(self) -> KeysView[str]:
        return self._devices.keys()

    def __len__(self) -> int:
        return len(self._devices)

    def __iter__(self) -> Iterator[str]:
        return iter(self._devices)

    def __contains__(self, label: str) -> bool:
        return label in self._devices

    def __getitem__(self, label: str) -> Device:
        if label not in self._devices:
            raise KeyError(f"No device with label '{label!r}'")
        return self._devices[label]

    def get_device(self, label: str) -> Device:
        return self[label]

    def get(self, label: str) -> Device | None:
        return self._devices.get(label, None)

    @overload
    def require_device_type(
        self, label: str, *types: Literal[DeviceType.XYStage]
    ) -> XYStageDevice: ...
    @overload
    def require_device_type(
        self, label: str, *types: Literal[DeviceType.Stage]
    ) -> StageDevice: ...
    @overload
    def require_device_type(
        self, label: str, *types: Literal[DeviceType.XYStage, DeviceType.Stage]
    ) -> _BaseStage: ...

    @overload
    def require_device_type(self, label: str, *types: DeviceType) -> Device: ...

    def require_device_type(self, label: str, *types: DeviceType) -> Device:
        device = self[label]
        if device.type() not in types:
            # TODO: change to something like CMMError
            raise ValueError(
                f"Device {label!r} is of the wrong type for the requested operation"
            )
        return device
