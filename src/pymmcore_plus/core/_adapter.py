from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from pymmcore import DeviceType

from ._device import Device

if TYPE_CHECKING:
    from ._mmcore_plus import CMMCorePlus


class AvailableDevice(NamedTuple):
    name: str
    type: DeviceType
    description: str
    core: CMMCorePlus

    def load(self, label: str) -> Device:
        """Load the device under the label `label`."""
        self._mmc.loadDevice(self.name, label)

class Adapter:
    """Convenience view onto a device adapter library.

    This is the type of object that is returned by
    [`pymmcore_plus.CMMCorePlus.getAdapterObject`][]

    Parameters
    ----------
    library_name : str
        Device this property belongs to
    mmcore : CMMCorePlus
        CMMCorePlus instance

    """

    def __init__(self, library_name: str, mmcore: CMMCorePlus) -> None:
        self.library = library_name
        self._mmc = mmcore
        # self.propertyChanged = _DevicePropValueSignal(device_label, None, mmcore)

    @property
    def core(self) -> CMMCorePlus:
        """Return the `CMMCorePlus` instance to which this Device is bound."""
        return self._mmc

    @property
    def available_devices(self) -> tuple[AvailableDevice, ...]:
        """Get all properties supported by device as DeviceProperty objects."""
        devs = self._mmc.getAvailableDevices(self.library)
        types = self._mmc.getAvailableDeviceTypes(self.library)
        descriptions = self._mmc.getAvailableDeviceDescriptions(self.library)
        return tuple(
            AvailableDevice(label, DeviceType(dt), desc, self._mmc)
            for label, dt, desc in zip(devs, types, descriptions)
        )
