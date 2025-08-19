from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, TypeVar, cast

from pymmcore_plus.core._constants import DeviceInitializationState, DeviceType

from .devices._device_base import Device

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pymmcore import DeviceLabel

    from ._proxy import CMMCoreProxy

DevT = TypeVar("DevT", bound=Device)
logger = logging.getLogger(__name__)


class PyDeviceManager:
    """Manages loaded Python devices."""

    __slots__ = ("_devices",)

    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}

    def load(self, label: str, device: Device, proxy: CMMCoreProxy) -> None:
        """Load a device and assign it a label."""
        if label in self._devices:  # pragma: no cover
            # we probably won't ever get here because the core checks this too
            raise ValueError(f"The specified device label {label!r} is already in use")
        self._devices[label] = device
        device._label_ = label
        device._core_proxy_ = proxy

    def initialize(self, label: str) -> None:
        """Initialize the device with the given label."""
        device = self[label]
        try:
            device.initialize()
            device._initialized_ = True
        except Exception as e:
            device._initialized_ = e
            logger.exception(f"Failed to initialize device {label!r}")

    def initialize_all(self) -> None:
        if not (labels := self.get_labels_of_type(DeviceType.Any)):
            return  # pragma: no cover

        # Initialize all devices in parallel
        with ThreadPoolExecutor() as executor:
            for future in as_completed(
                executor.submit(self.initialize, label) for label in labels
            ):
                future.result()

    def wait_for(
        self, label: str, timeout_ms: float = 5000, polling_interval: float = 0.01
    ) -> None:
        """Wait for the device to not be busy."""
        device = self[label]
        deadline = time.perf_counter() + timeout_ms / 1000

        while True:
            with device:
                if not device.busy():
                    return
            if time.perf_counter() > deadline:
                raise TimeoutError(
                    f"Wait for device {label!r} timed out after {timeout_ms} ms"
                )
            time.sleep(polling_interval)

    def wait_for_device_type(self, dev_type: int, timeout_ms: float = 5000) -> None:
        if not (labels := self.get_labels_of_type(dev_type)):
            return  # pragma: no cover

        # Wait for all python devices of the given type in parallel
        with ThreadPoolExecutor() as executor:
            futures = (
                executor.submit(self.wait_for, lbl, timeout_ms) for lbl in labels
            )
            for future in as_completed(futures):
                future.result()  # Raises any exceptions from wait_for_device

    def get_initialization_state(self, label: str) -> DeviceInitializationState:
        """Return the initialization state of the device with the given label."""
        state = self[label]._initialized_
        if state is True:
            return DeviceInitializationState.InitializedSuccessfully
        if state is False:
            return DeviceInitializationState.Uninitialized
        return DeviceInitializationState.InitializationFailed

    def unload(self, label_or_device: str | Device) -> None:
        """Unload a loaded device by label or instance."""
        if isinstance(label_or_device, Device):
            if label_or_device not in self._devices.values():
                raise ValueError("Device instance is not loaded")  # pragma: no cover
            _device, label = label_or_device, label_or_device._label_
        else:
            _device, label = self[label_or_device], label_or_device

        with _device as dev:
            dev.shutdown()
            dev._initialized_ = False
            dev._label_ = ""
            dev._core_proxy_ = None
        self._devices.pop(label)

    def unload_all(self) -> None:
        """Unload all loaded devices."""
        for label in list(self._devices):
            self.unload(label)

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

    def get_initialized(
        self, label: str, *, require_initialized: bool = True
    ) -> Device:
        """Get device by label, returning None if it does not exist.

        This method is a convenience wrapper around __getitem__ that ensures the device
        is both loaded and initialized.
        """
        if (device := self[label])._initialized_ is not True and require_initialized:
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
            f"Device {label!r} is the wrong device type for the requested operation"
        )

    def get_labels_of_type(self, dev_type: int) -> tuple[DeviceLabel, ...]:
        """Get the labels of all devices that are instances of the given type(s)."""
        return tuple(
            cast("DeviceLabel", label)
            for label, device in self._devices.items()
            if dev_type == DeviceType.Any or device.type() == dev_type
        )
