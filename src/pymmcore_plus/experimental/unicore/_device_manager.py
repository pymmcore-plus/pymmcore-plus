from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar, cast, overload

from pymmcore_plus.core._constants import DeviceInitializationState, DeviceType

from .devices._device import Device

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pymmcore import DeviceLabel

T = TypeVar("T")
DevT = TypeVar("DevT", bound=Device)
logger = logging.getLogger(__name__)


class NULL:
    """Sentinel value for default arguments."""

    def __bool__(self) -> bool:
        return False


_NULL = NULL()


class PyDeviceManager:
    """Manages loaded Python devices."""

    __slots__ = ("_devices",)

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
        with self._devices[label] as dev:
            dev.shutdown()
            dev._initialized = False  # noqa: SLF001
        self._devices.pop(label)

    def unload_all_devices(self) -> None:
        """Unload all loaded devices."""
        for label in list(self._devices):
            self.unload_device(label)

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

    @overload
    def get(self, label: str, *, require_initialized: bool = ...) -> Device: ...
    @overload
    def get(
        self, label: str, default: T, *, require_initialized: bool = ...
    ) -> Device | T: ...
    def get(
        self, label: str, default: T | NULL = _NULL, *, require_initialized: bool = True
    ) -> Device | T:
        """Get device by label, returning None if it does not exist."""
        if label not in self._devices:
            if isinstance(default, NULL):
                raise KeyError(f"No device with label '{label!r}'")
            return default
        device = self._devices[label]
        if require_initialized and device._initialized is not True:  # noqa: SLF001
            raise ValueError(f"Device {label!r} is not initialized")
        return device

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
            if dev_type == DeviceType.Any or device.type() == dev_type
        )
