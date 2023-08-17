from __future__ import annotations

from typing import TYPE_CHECKING

from pymmcore_plus.core._constants import DeviceType
from pymmcore_plus.core._device import Device

if TYPE_CHECKING:
    from ._mmcore_plus import CMMCorePlus


class DeviceAdapter:
    """Convenience view onto a device-adapter library.

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
        self._name = library_name
        self._mmc = mmcore
        # self.propertyChanged = _DevicePropValueSignal(device_label, None, mmcore)

    @property
    def name(self) -> str:
        """Return the short name of this device adapter library."""
        return self._name

    @property
    def core(self) -> CMMCorePlus:
        """Return the `CMMCorePlus` instance to which this Device is bound."""
        return self._mmc

    @property
    def available_devices(self) -> tuple[Device, ...]:
        """Get available devices offered by this device adapter.

        Returns
        -------
        tuple[Device, ...]
            Tuple of `Device` objects, with the name, type, and description
            of each device.  These objects also have a `load` method that can be used
            to load the device under a given label.
        """
        try:
            devs = self._mmc.getAvailableDevices(self.name)
        except RuntimeError:
            return ()

        types = self._mmc.getAvailableDeviceTypes(self.name)
        descriptions = self._mmc.getAvailableDeviceDescriptions(self.name)
        return tuple(
            Device(
                mmcore=self._mmc,
                adapter_name=self.name,
                device_name=dev_name,
                type=DeviceType(dt),
                description=desc,
            )
            for dev_name, dt, desc in zip(devs, types, descriptions)
        )

    @property
    def loaded_devices(self) -> tuple[Device, ...]:
        """Get currently loaded devices controlled this adapter.

        Returns
        -------
        tuple[Device, ...]
            Tuple of loaded `Device` objects.
        """
        return tuple(self._mmc.iterDevices(device_adapter=self.name))

    def unload(self) -> None:
        """Forcefully unload this library."""
        self._mmc.unloadLibrary(self.name)

    def __repr__(self) -> str:
        """Return string representation of this adapter."""
        core = repr(self._mmc).strip("<>")
        try:
            ndevs = str(len(self._mmc.getAvailableDevices(self.name)))
        except Exception:
            ndevs = "ERR"
        return f"<Adapter {self.name!r} on {core}: {ndevs} devices>"
