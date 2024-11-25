from pymmcore_plus.core._pycore import UniMMCore, XYStageDevice


class MyStage(XYStageDevice):
    """Example XY stage device."""

    _pos = (0.0, 0.0)

    def set_position(self, x: float, y: float) -> None:
        """Set the position of the stage."""
        print("  setting in python")
        self._pos = (x, y)

    def get_position(self) -> tuple[float, float]:
        """Get the current position of the stage."""
        print("  getting position in python")
        return self._pos


core = UniMMCore()
core.loadSystemConfiguration()
# print status of C-side XY stage device
print(f"core XY device is {core.getXYStageDevice()!r}")
core.setXYPosition(100, 200)
print(f"pos: {core.getXYPosition()}")

# load a python XY stage device
core.load_py_device("pyXY", MyStage())
# set the core XY stage device to the python device, dropping the C-side device
core.setXYStageDevice("pyXY")

print(f"core XY device is {core.getXYStageDevice()!r}")
core.setXYPosition(10, 20)
print(f"pos: {core.getXYPosition()}")

# can still set and query the C-side device directly
core.waitForDevice("XY")
core.setXYPosition("XY", 1.5, 3.7)
print(f"XY pos: {core.getXYPosition("XY")}")
print(f"pyXY pos: {core.getXYPosition("pyXY")}")
