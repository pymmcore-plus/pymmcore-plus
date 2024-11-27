from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, NewType, cast, overload

from pymmcore_plus.core import CMMCorePlus, Keyword
from pymmcore_plus.core import DeviceType as DT
from pymmcore_plus.core import Keyword as KW

from ._device_manager import PyDeviceManager

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pymmcore import DeviceLabel

    PyDeviceLabel = NewType("PyDeviceLabel", DeviceLabel)

    from pymmcore_plus.unicore._device import Device


class _CoreDevice:
    """A virtual core device.

    This mirrors the pattern used in CMMCore, where there is a virtual "core" device
    that maintains state about various "current" (real) devices.  When a call is made to
    `setSomeThing()` without specifying a device label, the CoreDevice is used to
    determine which real device to use.
    """

    def __init__(self) -> None:
        self._pycurrent: dict[Keyword, PyDeviceLabel | None] = {
            KW.CoreCamera: None,
            KW.CoreShutter: None,
            KW.CoreFocus: None,
            KW.CoreXYStage: None,
            KW.CoreAutoFocus: None,
            KW.CoreSLM: None,
            KW.CoreGalvo: None,
        }

    def current(self, keyword: Keyword) -> PyDeviceLabel | None:
        return self._pycurrent[keyword]

    def set_current(self, keyword: Keyword, label: str | None) -> None:
        self._pycurrent[keyword] = cast("PyDeviceLabel", label)


class UniMMCore(CMMCorePlus):
    """Unified Core object that first checks for python, then C++ devices."""

    def __init__(self, mm_path: str | None = None, adapter_paths: Sequence[str] = ()):
        super().__init__(mm_path, adapter_paths)
        self._pydevices = PyDeviceManager()
        self._pycore = _CoreDevice()

    def load_py_device(self, label: str, device: Device) -> None:
        # prevent conflicts with CMMCore device names
        if label in self.getLoadedDevices():
            raise ValueError(f"The specified device label {label!r} is already in use")
        self._pydevices.load_device(label, device)

    def _set_current_if_pydevice(self, keyword: Keyword, label: str) -> str:
        """Helper function to set the current core device if it is a python device.

        If the label is a python device, the current device is set and the label is
        cleared (in preparation for calling `super().setDevice()`), otherwise the
        label is returned unchanged.
        """
        if label in self._pydevices:
            self._pycore.set_current(keyword, label)
            label = ""
        return label

    # -----------------------------------------------------------------------
    # ---------------------------- XYStageDevice ----------------------------
    # -----------------------------------------------------------------------

    def setXYStageDevice(self, xyStageLabel: DeviceLabel | str) -> None:
        label = self._set_current_if_pydevice(KW.CoreXYStage, xyStageLabel)
        super().setXYStageDevice(label)

    def getXYStageDevice(self) -> DeviceLabel | Literal[""]:
        """Returns the label of the currently selected XYStage device.

        Returns empty string if no XYStage device is selected.
        """
        return self._pycore.current(KW.CoreXYStage) or super().getXYStageDevice()

    @overload
    def setXYPosition(self, x: float, y: float, /) -> None: ...
    @overload
    def setXYPosition(self, xyStageLabel: str, x: float, y: float, /) -> None: ...
    def setXYPosition(self, *args: Any) -> None:
        if len(args) == 3:
            label, x, y = args
        elif len(args) == 2:
            x, y = args
            label = self.getXYStageDevice()

        if label not in self._pydevices:
            return super().setXYPosition(label, x, y)

        with self._pydevices.require_device_type(label, DT.XYStage) as dev:
            dev.set_position_um(x, y)

    @overload
    def getXYPosition(self) -> tuple[float, float]: ...
    @overload
    def getXYPosition(self, xyStageLabel: DeviceLabel | str) -> tuple[float, float]: ...
    def getXYPosition(
        self, xyStageLabel: DeviceLabel | str = ""
    ) -> tuple[float, float]:
        """Obtains the current position of the XY stage in microns."""
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:
            return tuple(super().getXYPosition(label))  # type: ignore

        with self._pydevices.require_device_type(label, DT.XYStage) as dev:
            return dev.get_position_um()

    @overload
    def getXPosition(self) -> float: ...
    @overload
    def getXPosition(self, xyStageLabel: DeviceLabel | str) -> float: ...
    def getXPosition(self, xyStageLabel: DeviceLabel | str = "") -> float:
        """Obtains the current position of the X axis of the XY stage in microns."""
        return self.getXYPosition(xyStageLabel)[0]

    @overload
    def getYPosition(self) -> float: ...
    @overload
    def getYPosition(self, xyStageLabel: DeviceLabel | str) -> float: ...
    def getYPosition(self, xyStageLabel: DeviceLabel | str = "") -> float:
        """Obtains the current position of the Y axis of the XY stage in microns."""
        return self.getXYPosition(xyStageLabel)[1]

    def getXYStageSequenceMaxLength(self, xyStageLabel: DeviceLabel | str) -> int:
        """Gets the maximum length of an XY stage's position sequence."""
        return super().getXYStageSequenceMaxLength(xyStageLabel)

    def isXYStageSequenceable(self, xyStageLabel: DeviceLabel | str) -> bool:
        """Queries XY stage if it can be used in a sequence."""
        return super().isXYStageSequenceable(xyStageLabel)

    def loadXYStageSequence(
        self,
        xyStageLabel: DeviceLabel | str,
        xSequence: Sequence[float],
        ySequence: Sequence[float],
        /,
    ) -> None:
        """Transfer a sequence of stage positions to the xy stage.

        xSequence and ySequence must have the same length. This should only be called
        for XY stages that are sequenceable
        """
        super().loadXYStageSequence(xyStageLabel, xSequence, ySequence)

    @overload
    def setOriginX(self) -> None: ...
    @overload
    def setOriginX(self, xyStageLabel: DeviceLabel | str) -> None: ...
    def setOriginX(self, xyStageLabel: DeviceLabel | str = "") -> None:
        """Zero the given XY stage's X coordinate at the current position."""
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:
            return super().setOriginX(label)

        with self._pydevices.require_device_type(label, DT.XYStage) as dev:
            dev.set_origin_x()

    @overload
    def setOriginY(self) -> None: ...
    @overload
    def setOriginY(self, xyStageLabel: DeviceLabel | str) -> None: ...
    def setOriginY(self, xyStageLabel: DeviceLabel | str = "") -> None:
        """Zero the given XY stage's Y coordinate at the current position."""
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:
            return super().setOriginY(label)

        with self._pydevices.require_device_type(label, DT.XYStage) as dev:
            dev.set_origin_y()

    @overload
    def setOriginXY(self) -> None: ...
    @overload
    def setOriginXY(self, xyStageLabel: DeviceLabel | str) -> None: ...
    def setOriginXY(self, xyStageLabel: DeviceLabel | str = "") -> None:
        """Zero the given XY stage's coordinates at the current position."""
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:
            return super().setOriginXY(label)

        with self._pydevices.require_device_type(label, DT.XYStage) as dev:
            dev.set_origin()

    @overload
    def setAdapterOriginXY(self, newXUm: float, newYUm: float, /) -> None: ...
    @overload
    def setAdapterOriginXY(
        self, xyStageLabel: DeviceLabel | str, newXUm: float, newYUm: float, /
    ) -> None: ...
    def setAdapterOriginXY(self, *args: Any) -> None:
        """Enable software translation of coordinates for the current XY stage.

        The current position of the stage becomes (newXUm, newYUm). It is recommended
        that setOriginXY() be used instead where available.
        """
        if len(args) == 3:
            label, x, y = args
        elif len(args) == 2:
            x, y = args
            label = self.getXYStageDevice()

        if label not in self._pydevices:
            return super().setAdapterOriginXY(label, x, y)

        with self._pydevices.require_device_type(label, DT.XYStage) as dev:
            dev.set_adapter_origin_um(x, y)

    @overload
    def setRelativeXYPosition(self, dx: float, dy: float, /) -> None: ...
    @overload
    def setRelativeXYPosition(
        self, xyStageLabel: DeviceLabel | str, dx: float, dy: float, /
    ) -> None: ...
    def setRelativeXYPosition(self, *args: Any) -> None:
        """Sets the relatizve position of the XY stage in microns."""
        super().setRelativeXYPosition(*args)

    def startXYStageSequence(self, xyStageLabel: DeviceLabel | str) -> None:
        """Starts an ongoing sequence of triggered events in an XY stage.

        This should only be called for stages
        """
        super().startXYStageSequence(xyStageLabel)

    def stopXYStageSequence(self, xyStageLabel: DeviceLabel | str) -> None:
        """Stops an ongoing sequence of triggered events in an XY stage.

        This should only be called for stages that are sequenceable
        """
        super().stopXYStageSequence(xyStageLabel)

    # -----------------------------------------------------------------------
    # ---------------------------- Any Stage --------------------------------
    # -----------------------------------------------------------------------

    def home(self, xyOrZStageLabel: DeviceLabel | str) -> None:
        """Perform a hardware homing operation for an XY or focus/Z stage."""
        if (dev := self._pydevices.get(xyOrZStageLabel)) is None:
            return super().home(xyOrZStageLabel)

        dev = self._pydevices.require_device_type(xyOrZStageLabel, DT.XYStage, DT.Stage)
        dev.home()

    def stop(self, xyOrZStageLabel: DeviceLabel | str) -> None:
        """Stop the XY or focus/Z stage."""
        if (dev := self._pydevices.get(xyOrZStageLabel)) is None:
            return super().stop(xyOrZStageLabel)

        dev = self._pydevices.require_device_type(xyOrZStageLabel, DT.XYStage, DT.Stage)
        dev.stop()
