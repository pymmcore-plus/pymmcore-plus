from __future__ import annotations

import time
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

    # -- Bridge protocol --

    def fire(self, delta_t: float) -> None:
        """Open shutter for delta_t milliseconds, then close."""
        self.set_open(True)
        time.sleep(delta_t / 1000.0)
        self.set_open(False)
