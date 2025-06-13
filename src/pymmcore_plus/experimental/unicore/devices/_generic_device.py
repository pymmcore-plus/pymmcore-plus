from pymmcore_plus.core._constants import DeviceType

from ._device_base import Device


class GenericDevice(Device):
    """Generic device API, e.g. for devices that don't fit into other categories.

    Generic Devices generally only use the device property interface.
    """

    _TYPE = DeviceType.GenericDevice
