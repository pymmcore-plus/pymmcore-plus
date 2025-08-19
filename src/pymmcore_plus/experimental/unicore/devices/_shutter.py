from __future__ import annotations

from abc import abstractmethod

from pymmcore_plus.core._constants import DeviceType

from ._device_base import Device


class ShutterDevice(Device):
    """Shutter device API, e.g. for physical shutters or electronic shutter control.

    Or any 2-state device that can be either open or closed.
    """

    _TYPE = DeviceType.ShutterDevice

    @abstractmethod
    def get_open(self) -> bool:
        """Return True if the shutter is open, False if it is closed."""

    @abstractmethod
    def set_open(self, open: bool) -> None:
        """Set the shutter to open or closed.

        Parameters
        ----------
        open : bool
            True to open the shutter, False to close it.
        """
