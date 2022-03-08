from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from ._property import DeviceProperty
from .events._device_signal_view import _DevicePropValueSignal

if TYPE_CHECKING:
    from ._constants import DeviceDetectionStatus, DeviceType
    from ._mmcore_plus import CMMCorePlus


class Device:
    """Convenience view onto a device.

    Parameters
    ----------
    device_label : str
        Device this property belongs to
    mmcore : CMMCorePlus
        CMMCorePlus instance

    Examples
    --------
    >>> core = CMMCorePlus()
    >>> device = Device('Camera', core)
    >>> device.isLoaded()
    >>> device.load('NotALib', 'DCam')  # useful error
    >>> device.load('DemoCamera', 'DCam')
    >>> device.initialize()
    >>> device.load('DemoCamera', 'DCam')  # no-op w/ useful warning
    >>> device.properties  # tuple of DeviceProperty objects
    >>> device.description()
    >>> device.isBusy()
    >>> device.wait()
    >>> device.type()
    >>> device.schema()  # JSON schema of device properties
    """

    def __init__(self, device_label: str, mmcore: CMMCorePlus) -> None:
        self.label = device_label
        self._mmc = mmcore
        self.propertyChanged = _DevicePropValueSignal(device_label, None, mmcore)

    @property
    def core(self) -> CMMCorePlus:
        """Return the core instance to which this Device is bound."""
        return self._mmc

    def isBusy(self) -> bool:
        """Return busy status for this device."""
        return self._mmc.deviceBusy(self.label)

    def delayMs(self) -> float:
        """Return action delay in ms for this device"""
        return self._mmc.getDeviceDelayMs(self.label)

    def setDelayMs(self, delayMs: float):
        """Override the built-in value for the action delay."""
        self._mmc.setDeviceDelayMs(self.label, delayMs)

    def usesDelay(self) -> bool:
        """Return `True` if the device will use the delay setting or not."""
        return self._mmc.usesDeviceDelay(self.label)

    def description(self) -> str:
        """Return device description."""
        return self._mmc.getDeviceDescription(self.label)

    def library(self) -> str:
        """Return device library (aka module, device adapter) name."""
        return self._mmc.getDeviceLibrary(self.label)

    def name(self) -> str:
        """Returns device name (this is not the same as the device label)."""
        return self._mmc.getDeviceName(self.label)

    def propertyNames(self) -> Tuple[str, ...]:
        """Return all property names supported by this device."""
        return self._mmc.getDevicePropertyNames(self.label)

    @property
    def properties(self) -> Tuple[DeviceProperty, ...]:
        """Get all properties supported by device as DeviceProperty objects."""
        return tuple(
            DeviceProperty(self.label, name, self._mmc) for name in self.propertyNames()
        )

    def initialize(self) -> None:
        """Initialize device."""
        return self._mmc.initializeDevice(self.label)

    def load(self, adapter_name: str, device_name: str) -> None:
        """Load device from the plugin library.

        Parameters
        ----------
        adapter_name : str
            The name of the device adapter module (short name, not full file name).
            (This is what is returned by `Device.library()`)
        device_name : str
            The name of the device. The name must correspond to one of the names
            recognized by the specific plugin library. (This is what is returned by
            `Device.name()`)
        """
        try:
            self._mmc.loadDevice(self.label, adapter_name, device_name)
        except RuntimeError as e:
            msg = str(e)
            if self.isLoaded():
                if adapter_name == self.library() and device_name == self.name():
                    msg += f". Device {self.label!r} appears to be loaded already."
                    import warnings

                    warnings.warn(msg)
                    return
                lib = self._mmc.getDeviceLibrary(self.label)
                name = self._mmc.getDeviceName(self.label)
                msg += f". Device {self.label!r} is already taken by {lib}::{name}"
            else:
                adapters = self._mmc.getDeviceAdapterNames()
                if adapter_name not in adapters:
                    msg += (
                        f". Adapter name {adapter_name!r} not in list of "
                        f"known adapter names: {adapters}."
                    )
                else:
                    devices = self._mmc.getAvailableDevices(adapter_name)
                    if device_name not in devices:
                        msg += (
                            f". Device name {device_name!r} not in devices provided by "
                            f"adapter {adapter_name!r}: {devices}"
                        )
            raise RuntimeError(msg)  # sourcery skip

    def unload(self):
        """Unload device from the core and adjust all configuration data."""
        return self._mmc.unloadDevice(self.label)

    def isLoaded(self) -> bool:
        """Return `True` if device is loaded."""
        return self.label in self._mmc.getLoadedDevices()

    def detect(self) -> DeviceDetectionStatus:
        """Tries to communicate to device through a given serial port.

        Used to automate discovery of correct serial port. Also configures the
        serial port correctly.
        """
        return self._mmc.detectDevice(self.label)

    def supportsDetection(self) -> bool:
        """Return whether or not the device supports automatic device detection.

        (i.e. whether or not detectDevice() may be safely called).
        """
        try:
            return self._mmc.supportsDeviceDetection(self.label)
        except RuntimeError:
            return False  # e.g. core devices

    def type(self) -> DeviceType:
        """Return device type."""
        return self._mmc.getDeviceType(self.label)

    def schema(self) -> dict:
        """Return dict in JSON-schema format for properties of `device_label`."""
        return self._mmc.getDeviceSchema(self.label)

    def wait(self) -> None:
        """Block the calling thread until device becomes non-busy."""
        self._mmc.waitForDevice(self.label)

    def __repr__(self) -> str:
        if self.isLoaded():
            n = len(self.propertyNames())
            props = f'{n} propertie{"s" if n>1 else ""}'
            lib = f"({self.library()}::{self.name()}) "
        else:
            props = "NOT LOADED"
            lib = ""
        core = repr(self._mmc).strip("<>")
        return f"<Device {self.label!r} {lib}on {core}: {props}>"
