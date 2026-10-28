from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal

from pymmcore_plus.core._constants import DeviceType

from ._device_base import Device

if TYPE_CHECKING:
    from collections.abc import Sequence


class HubDevice(Device):
    """ABC for Hub devices that can have peripheral devices attached.

    Hub devices represent a central device (e.g., a controller) that can have
    multiple peripheral devices attached to it. Examples include multi-channel
    controllers, or devices that manage multiple sub-devices.

    Override `detect_installed_devices()` to return peripheral devices:

    ```python
    class MyHub(HubDevice):
        def detect_installed_devices(
            self,
        ) -> Sequence[tuple[str, Device, DeviceType]]:
            return [
                ("Motor1", Motor1Device(), DeviceType.Stage),
                ("Motor2", Motor2Device(), DeviceType.Stage),
            ]
    ```
    """

    _TYPE: ClassVar[Literal[DeviceType.Hub]] = DeviceType.Hub

    def detect_installed_devices(
        self,
    ) -> Sequence[tuple[str, Device, DeviceType]]:
        """Return peripheral devices installed on this hub.

        Returns
        -------
        Sequence[tuple[str, Device, DeviceType]]
            A sequence of (name, device_instance, device_type) tuples.
            The C++ bridge uses these to register real devices.
        """
        return ()
