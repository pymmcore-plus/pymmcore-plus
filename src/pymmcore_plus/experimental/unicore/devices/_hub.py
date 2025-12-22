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

    To implement a Hub device, simply override `get_installed_peripherals()`:

    ```python
    class MyHub(HubDevice):
        def get_installed_peripherals(self) -> Sequence[tuple[str, str]]:
            return [
                ("Motor1", "First motor controller"),
                ("Motor2", "Second motor controller"),
            ]
    ```

    If your hub needs to perform expensive detection (e.g., scanning a bus),
    implement caching inside your `get_installed_peripherals()` method.
    """

    _TYPE: ClassVar[Literal[DeviceType.Hub]] = DeviceType.Hub

    def get_installed_peripherals(self) -> Sequence[tuple[str, str]]:
        """Return information about installed peripheral devices.

        Override this method to return a sequence of `tuple[str, str]` objects
        describing all devices that can be loaded as peripherals of this hub.

        Returns
        -------
        Sequence[tuple[str, str]]
            A sequence of (name, description) tuples for each available peripheral.
            The name MUST be the name of a class, importable from the same module as
            this hub.
        """
        return ()
