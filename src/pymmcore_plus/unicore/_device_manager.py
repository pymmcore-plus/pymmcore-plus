from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar, cast

from pymmcore_plus.core._constants import DeviceInitializationState

from ._device import Device

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pymmcore import DeviceLabel


DevT = TypeVar("DevT", bound=Device)
logger = logging.getLogger(__name__)


class PyDeviceManager:
    """Manages loaded Python devices."""

    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}

    def load_device(self, label: str, device: Device) -> None:
        """Load a device and assign it a label."""
        if label in self._devices:
            raise ValueError(f"The specified device label {label!r} is already in use")
        # TODO other stuff
        self._devices[label] = device

    def initialize_device(self, label: str) -> None:
        """Initialize the device with the given label."""
        device = self[label]
        try:
            # we're setting this *just* before calling initialize so that
            # properties registered in the initialize method can know that they are
            # NOT pre-init propss
            device._initialized = True  # noqa: SLF001
            device.initialize()
        except Exception as e:
            device._initialized = e  # noqa: SLF001
            logger.exception(f"Failed to initialize device {label!r}")

    def get_device_initialization_state(self, label: str) -> DeviceInitializationState:
        """Return the initialization state of the device with the given label."""
        state = self[label]._initialized  # noqa: SLF001
        if state is True:
            return DeviceInitializationState.InitializedSuccessfully
        if state is False:
            return DeviceInitializationState.Uninitialized
        return DeviceInitializationState.InitializationFailed

    def unload_device(self, device: str | Device) -> None:
        """Unload a loaded device by label or instance."""
        if isinstance(device, Device):
            label = next((k for k, v in self._devices.items() if v is device), None)
        else:
            label = device
        if label not in self._devices:
            raise KeyError(f"No device with label '{label!r}'")
        self._devices.pop(label)

    def unload_all_devices(self) -> None:
        """Unload all loaded devices."""
        self._devices.clear()  # TODO ...

    def __len__(self) -> int:
        """Return the number of loaded device labels."""
        return len(self._devices)

    def __iter__(self) -> Iterator[DeviceLabel]:
        """Return an iterator over the loaded device labels."""
        return iter(self._devices)  # type: ignore

    def __contains__(self, label: str) -> bool:
        """Return True if the device with the given label is loaded."""
        return label in self._devices

    def __getitem__(self, label: str) -> Device:
        """Get device by label, raising KeyError if it does not exist."""
        if label not in self._devices:
            raise KeyError(f"No device with label '{label!r}'")
        return self._devices[label]

    def get(self, label: str) -> Device | None:
        """Get device by label, returning None if it does not exist."""
        return self._devices.get(label, None)

    def get_device_of_type(self, label: str, *types: type[DevT]) -> DevT:
        """Get device by label, ensuring it is of the correct type.

        Parameters
        ----------
        label : str
            The label of the device to retrieve.
        types : type[DevT]
            The type(s) the device must be an instance of.
        """
        device = self[label]
        if isinstance(device, types):
            return device
        raise ValueError(
            f"Device {label!r} is of the wrong type for the requested operation"
        )

    def get_labels_of_type(self, dev_type: int) -> tuple[DeviceLabel, ...]:
        """Get the labels of all devices that are instances of the given type(s)."""
        return tuple(
            cast("DeviceLabel", label)
            for label, device in self._devices.items()
            if device.type() == dev_type
        )
