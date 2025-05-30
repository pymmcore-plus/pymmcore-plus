from __future__ import annotations

from collections.abc import Sequence
from contextlib import suppress
from typing import TYPE_CHECKING, Any, cast, overload

from pymmcore_plus.core import CMMCorePlus, DeviceType
from pymmcore_plus.core import Keyword as KW
from pymmcore_plus.experimental.unicore._proxy import create_core_proxy
from pymmcore_plus.experimental.unicore.core._base_mixin import UniCoreBase
from pymmcore_plus.experimental.unicore.devices._device import Device
from pymmcore_plus.experimental.unicore.devices._stage import XYStageDevice, _BaseStage

from ._camera_mixin import PyCameraMixin

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Callable, Literal, NewType, TypeVar

    from pymmcore import AdapterName, DeviceLabel, DeviceName, PropertyName

    from pymmcore_plus.core._constants import DeviceInitializationState, PropertyType

    PyDeviceLabel = NewType("PyDeviceLabel", DeviceLabel)

    _T = TypeVar("_T")


class UniMMCore(PyCameraMixin, UniCoreBase):
    """Unified Core object that first checks for python, then C++ devices."""

    # -----------------------------------------------------------------------
    # ------------------------ General Core methods  ------------------------
    # -----------------------------------------------------------------------

    def reset(self) -> None:
        with suppress(TimeoutError):
            self.waitForSystem()
        self.unloadAllDevices()
        self._pycore.reset_current()
        super().reset()

    # -----------------------------------------------------------------------
    # ----------------- Functionality for All Devices ------------------------
    # -----------------------------------------------------------------------

    def loadDevice(
        self, label: str, moduleName: AdapterName | str, deviceName: DeviceName | str
    ) -> None:
        """Loads a device from the plugin library, or python module.

        In the standard MM case, this will load a device from the plugin library:

        ```python
        core.loadDevice("cam", "DemoCamera", "DCam")
        ```

        For python devices, this will load a device from a python module:

        ```python
        core.loadDevice("pydev", "package.module", "DeviceClass")
        ```

        """
        try:
            CMMCorePlus.loadDevice(self, label, moduleName, deviceName)
        except RuntimeError as e:
            # it was a C++ device, should have worked ... raise the error
            if moduleName not in super().getDeviceAdapterNames():
                pydev = self._get_py_device_instance(moduleName, deviceName)
                self.loadPyDevice(label, pydev)
                return
            if exc := self._load_error_with_info(label, moduleName, deviceName, str(e)):
                raise exc from e

    def _get_py_device_instance(self, module_name: str, cls_name: str) -> Device:
        """Import and instantiate a python device from `module_name.cls_name`."""
        try:
            module = __import__(module_name, fromlist=[cls_name])
        except ImportError as e:
            raise type(e)(
                f"{module_name!r} is not a known Micro-manager DeviceAdapter, or "
                "an importable python module "
            ) from e
        try:
            cls = getattr(module, cls_name)
        except AttributeError as e:
            raise AttributeError(
                f"Could not find class {cls_name!r} in python module {module_name!r}"
            ) from e
        if isinstance(cls, type) and issubclass(cls, Device):
            return cls()
        raise TypeError(f"{cls_name} is not a subclass of Device")

    def loadPyDevice(self, label: str, device: Device) -> None:
        """Load a `unicore.Device` as a python device.

        This API allows you to create python-side Device objects that can be used in
        tandem with the C++ devices. Whenever a method is called that would normally
        interact with a C++ device, this class will first check if a python device with
        the same label exists, and if so, use that instead.

        Parameters
        ----------
        label : str
            The label to assign to the device.
        device : unicore.Device
            The device object to load.  Use the appropriate subclass of `Device` for the
            type of device you are creating.
        """
        if label in self.getLoadedDevices():
            raise ValueError(f"The specified device label {label!r} is already in use")
        self._pydevices.load(label, device, create_core_proxy(self))

    load_py_device = loadPyDevice

    def unloadDevice(self, label: DeviceLabel | str) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().unloadDevice(label)
        self._pydevices.unload(label)

    def unloadAllDevices(self) -> None:
        self._pydevices.unload_all()
        super().unloadAllDevices()

    def initializeDevice(self, label: DeviceLabel | str) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().initializeDevice(label)
        return self._pydevices.initialize(label)

    def initializeAllDevices(self) -> None:
        super().initializeAllDevices()
        return self._pydevices.initialize_all()

    def getDeviceInitializationState(self, label: str) -> DeviceInitializationState:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDeviceInitializationState(label)
        return self._pydevices.get_initialization_state(label)

    def getLoadedDevices(self) -> tuple[DeviceLabel, ...]:
        return tuple(self._pydevices) + tuple(super().getLoadedDevices())

    def getLoadedDevicesOfType(self, devType: int) -> tuple[DeviceLabel, ...]:
        pydevs = self._pydevices.get_labels_of_type(devType)
        return pydevs + super().getLoadedDevicesOfType(devType)

    def getDeviceType(self, label: str) -> DeviceType:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDeviceType(label)
        return self._pydevices[label].type()

    def getDeviceLibrary(self, label: DeviceLabel | str) -> AdapterName:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDeviceLibrary(label)
        return cast("AdapterName", self._pydevices[label].__module__)

    def getDeviceName(self, label: DeviceLabel | str) -> DeviceName:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDeviceName(label)
        return cast("DeviceName", self._pydevices[label].name())

    def getDeviceDescription(self, label: DeviceLabel | str) -> str:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDeviceDescription(label)
        return self._pydevices[label].description()

    # ---------------------------- Properties ---------------------------

    def getDevicePropertyNames(
        self, label: DeviceLabel | str
    ) -> tuple[PropertyName, ...]:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDevicePropertyNames(label)
        names = tuple(self._pydevices[label].get_property_names())
        return cast("tuple[PropertyName, ...]", names)

    def hasProperty(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().hasProperty(label, propName)
        return propName in self._pydevices[label].get_property_names()

    def getProperty(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> Any:  # broadening to Any, because pydevices can return non-string values?
        if label not in self._pydevices:  # pragma: no cover
            return super().getProperty(label, propName)
        with self._pydevices[label] as dev:
            value = dev.get_property_value(propName)
            self._state_cache[(label, propName)] = value
        return value

    def getPropertyFromCache(
        self, deviceLabel: DeviceLabel | str, propName: PropertyName | str
    ) -> Any:
        if deviceLabel not in self._pydevices:
            return super().getPropertyFromCache(deviceLabel, propName)
        return self._state_cache[(deviceLabel, propName)]

    def setProperty(
        self, label: str, propName: str, propValue: bool | float | int | str
    ) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().setProperty(label, propName, propValue)
        with self._pydevices[label] as dev:
            dev.set_property_value(propName, propValue)
            self._state_cache[(label, propName)] = propValue

    def getPropertyType(self, label: str, propName: str) -> PropertyType:
        if label not in self._pydevices:  # pragma: no cover
            return super().getPropertyType(label, propName)
        return self._pydevices[label].property(propName).type

    def hasPropertyLimits(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().hasPropertyLimits(label, propName)
        with self._pydevices[label] as dev:
            return dev.property(propName).limits is not None

    def getPropertyLowerLimit(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> float:
        if label not in self._pydevices:  # pragma: no cover
            return super().getPropertyLowerLimit(label, propName)
        with self._pydevices[label] as dev:
            if lims := dev.property(propName).limits:
                return lims[0]
            return 0

    def getPropertyUpperLimit(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> float:
        if label not in self._pydevices:  # pragma: no cover
            return super().getPropertyUpperLimit(label, propName)
        with self._pydevices[label] as dev:
            if lims := dev.property(propName).limits:
                return lims[1]
            return 0

    def getAllowedPropertyValues(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> tuple[str, ...]:
        if label not in self._pydevices:  # pragma: no cover
            return super().getAllowedPropertyValues(label, propName)
        with self._pydevices[label] as dev:
            return tuple(dev.property(propName).allowed_values or ())

    def isPropertyPreInit(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().isPropertyPreInit(label, propName)
        with self._pydevices[label] as dev:
            return dev.property(propName).is_pre_init

    def isPropertyReadOnly(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().isPropertyReadOnly(label, propName)
        with self._pydevices[label] as dev:
            return dev.is_property_read_only(propName)

    def isPropertySequenceable(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().isPropertySequenceable(label, propName)
        with self._pydevices[label] as dev:
            return dev.is_property_sequenceable(propName)

    def getPropertySequenceMaxLength(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> int:
        if label not in self._pydevices:  # pragma: no cover
            return super().getPropertySequenceMaxLength(label, propName)
        with self._pydevices[label] as dev:
            return dev.property(propName).sequence_max_length

    def loadPropertySequence(
        self,
        label: DeviceLabel | str,
        propName: PropertyName | str,
        eventSequence: Sequence[Any],
    ) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().loadPropertySequence(label, propName, eventSequence)
        with self._pydevices[label] as dev:
            dev.load_property_sequence(propName, eventSequence)

    def startPropertySequence(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().startPropertySequence(label, propName)
        with self._pydevices[label] as dev:
            dev.start_property_sequence(propName)

    def stopPropertySequence(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().stopPropertySequence(label, propName)
        with self._pydevices[label] as dev:
            dev.stop_property_sequence(propName)

    # ------------------------------ Ready State ----------------------------

    def deviceBusy(self, label: DeviceLabel | str) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().deviceBusy(label)
        with self._pydevices[label] as dev:
            return dev.busy()

    def waitForDevice(self, label: DeviceLabel | str) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().waitForDevice(label)
        self._pydevices.wait_for(label, self.getTimeoutMs())

    # def waitForConfig

    # probably only needed because C++ method is not virtual
    def systemBusy(self) -> bool:
        return self.deviceTypeBusy(DeviceType.AnyType)

    # probably only needed because C++ method is not virtual
    def waitForSystem(self) -> None:
        self.waitForDeviceType(DeviceType.AnyType)

    def waitForDeviceType(self, devType: int) -> None:
        super().waitForDeviceType(devType)
        self._pydevices.wait_for_device_type(devType, self.getTimeoutMs())

    def deviceTypeBusy(self, devType: int) -> bool:
        if super().deviceTypeBusy(devType):
            return True

        for label in self._pydevices.get_labels_of_type(devType):
            with self._pydevices[label] as dev:
                if dev.busy():
                    return True
        return False

    def getDeviceDelayMs(self, label: DeviceLabel | str) -> float:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDeviceDelayMs(label)
        return 0  # pydevices don't yet support delays

    def setDeviceDelayMs(self, label: DeviceLabel | str, delayMs: float) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().setDeviceDelayMs(label, delayMs)
        if delayMs != 0:
            raise NotImplementedError("Python devices do not support delays")
        return

    def usesDeviceDelay(self, label: DeviceLabel | str) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().usesDeviceDelay(label)
        return False

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
    def setXYPosition(
        self, xyStageLabel: DeviceLabel | str, x: float, y: float, /
    ) -> None: ...
    def setXYPosition(self, *args: Any) -> None:
        """Sets the position of the XY stage in microns."""
        label, args = _ensure_label(args, min_args=3, getter=self.getXYStageDevice)
        if label not in self._pydevices:  # pragma: no cover
            return super().setXYPosition(label, *args)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.set_position_um(*args)

    @overload
    def getXYPosition(self) -> tuple[float, float]: ...
    @overload
    def getXYPosition(self, xyStageLabel: DeviceLabel | str) -> tuple[float, float]: ...
    def getXYPosition(
        self, xyStageLabel: DeviceLabel | str = ""
    ) -> tuple[float, float]:
        """Obtains the current position of the XY stage in microns."""
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:  # pragma: no cover
            return tuple(super().getXYPosition(label))  # type: ignore

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            return dev.get_position_um()

    # reimplementation needed because the C++ method are not virtual
    @overload
    def getXPosition(self) -> float: ...
    @overload
    def getXPosition(self, xyStageLabel: DeviceLabel | str) -> float: ...
    def getXPosition(self, xyStageLabel: DeviceLabel | str = "") -> float:
        """Obtains the current position of the X axis of the XY stage in microns."""
        return self.getXYPosition(xyStageLabel)[0]

    # reimplementation needed because the C++ method are not virtual
    @overload
    def getYPosition(self) -> float: ...
    @overload
    def getYPosition(self, xyStageLabel: DeviceLabel | str) -> float: ...
    def getYPosition(self, xyStageLabel: DeviceLabel | str = "") -> float:
        """Obtains the current position of the Y axis of the XY stage in microns."""
        return self.getXYPosition(xyStageLabel)[1]

    def getXYStageSequenceMaxLength(self, xyStageLabel: DeviceLabel | str) -> int:
        """Gets the maximum length of an XY stage's position sequence."""
        if xyStageLabel not in self._pydevices:  # pragma: no cover
            return super().getXYStageSequenceMaxLength(xyStageLabel)
        dev = self._pydevices.get_device_of_type(xyStageLabel, XYStageDevice)
        return dev.get_sequence_max_length()

    def isXYStageSequenceable(self, xyStageLabel: DeviceLabel | str) -> bool:
        """Queries XY stage if it can be used in a sequence."""
        if xyStageLabel not in self._pydevices:  # pragma: no cover
            return super().isXYStageSequenceable(xyStageLabel)
        dev = self._pydevices.get_device_of_type(xyStageLabel, XYStageDevice)
        return dev.is_sequenceable()

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
        if xyStageLabel not in self._pydevices:  # pragma: no cover
            return super().loadXYStageSequence(xyStageLabel, xSequence, ySequence)
        if len(xSequence) != len(ySequence):
            raise ValueError("xSequence and ySequence must have the same length")
        dev = self._pydevices.get_device_of_type(xyStageLabel, XYStageDevice)
        seq = tuple(zip(xSequence, ySequence))
        if len(seq) > dev.get_sequence_max_length():
            raise ValueError(
                f"Sequence is too long. Max length is {dev.get_sequence_max_length()}"
            )
        dev.send_sequence(seq)

    @overload
    def setOriginX(self) -> None: ...
    @overload
    def setOriginX(self, xyStageLabel: DeviceLabel | str) -> None: ...
    def setOriginX(self, xyStageLabel: DeviceLabel | str = "") -> None:
        """Zero the given XY stage's X coordinate at the current position."""
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:  # pragma: no cover
            return super().setOriginX(label)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.set_origin_x()

    @overload
    def setOriginY(self) -> None: ...
    @overload
    def setOriginY(self, xyStageLabel: DeviceLabel | str) -> None: ...
    def setOriginY(self, xyStageLabel: DeviceLabel | str = "") -> None:
        """Zero the given XY stage's Y coordinate at the current position."""
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:  # pragma: no cover
            return super().setOriginY(label)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.set_origin_y()

    @overload
    def setOriginXY(self) -> None: ...
    @overload
    def setOriginXY(self, xyStageLabel: DeviceLabel | str) -> None: ...
    def setOriginXY(self, xyStageLabel: DeviceLabel | str = "") -> None:
        """Zero the given XY stage's coordinates at the current position."""
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:  # pragma: no cover
            return super().setOriginXY(label)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
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
        label, args = _ensure_label(args, min_args=3, getter=self.getXYStageDevice)
        if label not in self._pydevices:  # pragma: no cover
            return super().setAdapterOriginXY(label, *args)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.set_adapter_origin_um(*args)

    @overload
    def setRelativeXYPosition(self, dx: float, dy: float, /) -> None: ...
    @overload
    def setRelativeXYPosition(
        self, xyStageLabel: DeviceLabel | str, dx: float, dy: float, /
    ) -> None: ...
    def setRelativeXYPosition(self, *args: Any) -> None:
        """Sets the relative position of the XY stage in microns."""
        label, args = _ensure_label(args, min_args=3, getter=self.getXYStageDevice)
        if label not in self._pydevices:  # pragma: no cover
            return super().setRelativeXYPosition(label, *args)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.set_relative_position_um(*args)

    def startXYStageSequence(self, xyStageLabel: DeviceLabel | str) -> None:
        """Starts an ongoing sequence of triggered events in an XY stage.

        This should only be called for stages that are sequenceable
        """
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:  # pragma: no cover
            return super().startXYStageSequence(label)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.start_sequence()

    def stopXYStageSequence(self, xyStageLabel: DeviceLabel | str) -> None:
        """Stops an ongoing sequence of triggered events in an XY stage.

        This should only be called for stages that are sequenceable
        """
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:  # pragma: no cover
            return super().stopXYStageSequence(label)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.stop_sequence()

    # -----------------------------------------------------------------------
    # ---------------------------- Any Stage --------------------------------
    # -----------------------------------------------------------------------

    def home(self, xyOrZStageLabel: DeviceLabel | str) -> None:
        """Perform a hardware homing operation for an XY or focus/Z stage."""
        if xyOrZStageLabel not in self._pydevices:
            return super().home(xyOrZStageLabel)

        dev = self._pydevices.get_device_of_type(xyOrZStageLabel, _BaseStage)
        dev.home()

    def stop(self, xyOrZStageLabel: DeviceLabel | str) -> None:
        """Stop the XY or focus/Z stage."""
        if xyOrZStageLabel not in self._pydevices:
            return super().stop(xyOrZStageLabel)

        dev = self._pydevices.get_device_of_type(xyOrZStageLabel, _BaseStage)
        dev.stop()


def _ensure_label(
    args: tuple[_T, ...], min_args: int, getter: Callable[[], str]
) -> tuple[str, tuple[_T, ...]]:
    """Ensure we have a device label.

    Designed to be used with overloaded methods that MAY take a device label as the
    first argument.

    If the number of arguments is less than `min_args`, the label is obtained from the
    getter function. If the number of arguments is greater than or equal to `min_args`,
    the label is the first argument and the remaining arguments are returned as a tuple
    """
    if len(args) < min_args:
        # we didn't get the label
        return getter(), args
    return cast("str", args[0]), args[1:]
