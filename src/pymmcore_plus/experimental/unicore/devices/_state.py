from typing import ClassVar, Literal

from pymmcore_plus.core._constants import DeviceType

from ._device import Device


class StateDevice(Device):
    """State device API, e.g. filter wheel, objective turret, etc."""

    _TYPE: ClassVar[Literal[DeviceType.State]] = DeviceType.State

    def set_position(self, pos: int | str) -> None:
        """Set the position of the device."""
        raise NotImplementedError

    def get_position_label() -> str:
        """Returns the label of the current position."""
        raise NotImplementedError

    #   // MMStateDevice API
    #   virtual int SetPosition(long pos) = 0;
    #   virtual int SetPosition(const char* label) = 0;
    #   virtual int GetPosition(long& pos) const = 0;
    #   virtual int GetPosition(char* label) const = 0;
    #   virtual int GetPositionLabel(long pos, char* label) const = 0;
    #   virtual int GetLabelPosition(const char* label, long& pos) const = 0;
    #   virtual int SetPositionLabel(long pos, const char* label) = 0;
    #   virtual unsigned long GetNumberOfPositions() const = 0;
    #   virtual int SetGateOpen(bool open = true) = 0;
    #   virtual int GetGateOpen(bool& open) = 0;
