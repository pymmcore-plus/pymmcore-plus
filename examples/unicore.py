"""Example of using combined C and Python devices in UniCore.

Unicore is a subclass of MMCore that allows for loading Python devices, which must be
subclasses of `pymmcore_plus.unicore.Device`. The final API is unchanged from
CMMCorePlus: the Unicore knows whether a device label corresponds to a C++ or Python
device and routes the call accordingly.

This example demonstrates how to create a custom Python stage device and use it together
with other C++ devices.
"""

from pymmcore_plus.experimental.unicore import UniMMCore, XYStageDevice, pymm_property


class MyStage(XYStageDevice):
    """Example XY stage device."""

    _pos = (0.0, 0.0)  # fake state, just used for this example

    # To know what methods to implement, see the abstractmethods in the base class
    # you are subclassing. (Note that it may also have unimplemented methods from
    # its own base classes, such as `stop` and `home` in this case.)

    def set_position_um(self, x: float, y: float) -> None:
        """Set the position of the stage."""
        print("  setting in python")
        self._pos = (x, y)

    def get_position_um(self) -> tuple[float, float]:
        """Get the current position of the stage."""
        print("  getting position in python")
        return self._pos

    def set_origin_x(self) -> None:
        pass

    def set_origin_y(self) -> None:
        pass

    def stop(self) -> None:
        print("STOP!")

    def home(self) -> None:
        print("HOME!")

    # Properties ---------------

    @pymm_property(limits=(0.0, 100.0), sequence_max_length=8)
    def propB(self) -> float:
        """Some custom property (Unused here... just an example)."""
        return 10.0

    @propB.setter
    def _set_prop_b(self, value: float) -> None:
        """Set propB."""


core = UniMMCore()
core.loadSystemConfiguration()

# print status of C-side XY stage device
print(f"core XY device is {core.getXYStageDevice()!r}")
core.setXYPosition(100, 200)
print(f"pos: {core.getXYPosition()}")

# load a python XY stage device
core.loadPyDevice("pyXY", MyStage())
core.initializeDevice("pyXY")
# set the core XY stage device to the python device, dropping the C-side device
core.setXYStageDevice("pyXY")

print(f"core XY device is {core.getXYStageDevice()!r}")
core.setXYPosition(10, 20)
print(f"pos: {core.getXYPosition()}")

# can still set and query the C-side device directly
core.waitForDevice("XY")
core.setXYPosition("XY", 1.5, 3.7)
print(f"XY pos: {core.getXYPosition('XY')}")
print(f"pyXY pos: {core.getXYPosition('pyXY')}")

core.home("pyXY")
core.stop("pyXY")
core.stop("XY")
