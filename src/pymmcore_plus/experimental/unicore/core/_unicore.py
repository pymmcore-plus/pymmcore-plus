from __future__ import annotations

import threading
import warnings
from collections.abc import Iterator, MutableMapping, Sequence
from contextlib import suppress
from datetime import datetime
from itertools import count
from time import perf_counter_ns
from typing import TYPE_CHECKING, Any, Callable, Literal, TypeVar, cast, overload

import numpy as np

import pymmcore_plus._pymmcore as pymmcore
from pymmcore_plus.core import CMMCorePlus, DeviceType, Keyword
from pymmcore_plus.core import Keyword as KW
from pymmcore_plus.core._constants import PixelType
from pymmcore_plus.experimental.unicore._device_manager import PyDeviceManager
from pymmcore_plus.experimental.unicore._proxy import create_core_proxy
from pymmcore_plus.experimental.unicore.devices._camera import Camera
from pymmcore_plus.experimental.unicore.devices._device import Device
from pymmcore_plus.experimental.unicore.devices._stage import XYStageDevice, _BaseStage

from ._sequence_buffer import SequenceBuffer

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Literal, NewType

    from numpy.typing import DTypeLike
    from pymmcore import AdapterName, AffineTuple, DeviceLabel, DeviceName, PropertyName

    from pymmcore_plus.core._constants import DeviceInitializationState, PropertyType

    PyDeviceLabel = NewType("PyDeviceLabel", DeviceLabel)
    _T = TypeVar("_T")


class BufferOverflowStop(Exception):
    """Exception raised to signal graceful stop on buffer overflow."""


CURRENT = {
    KW.CoreCamera: None,
    KW.CoreShutter: None,
    KW.CoreFocus: None,
    KW.CoreXYStage: None,
    KW.CoreAutoFocus: None,
    KW.CoreSLM: None,
    KW.CoreGalvo: None,
}


class _CoreDevice:
    """A virtual core device.

    This mirrors the pattern used in CMMCore, where there is a virtual "core" device
    that maintains state about various "current" (real) devices.  When a call is made to
    `setSomeThing()` without specifying a device label, the CoreDevice is used to
    determine which real device to use.
    """

    def __init__(self, state_cache: PropertyStateCache) -> None:
        self._state_cache = state_cache
        self._pycurrent: dict[Keyword, PyDeviceLabel | None] = {}
        self.reset_current()

    def reset_current(self) -> None:
        self._pycurrent.update(CURRENT)

    def current(self, keyword: Keyword) -> PyDeviceLabel | None:
        return self._pycurrent[keyword]

    def set_current(self, keyword: Keyword, label: str | None) -> None:
        self._pycurrent[keyword] = cast("PyDeviceLabel", label)
        self._state_cache[(KW.CoreDevice, keyword)] = label


class UniMMCore(CMMCorePlus):
    """Unified Core object that first checks for python, then C++ devices."""

    _DEFAULT_BUFFER_SIZE_MB: int = 1000  # default size of the sequence buffer in MB

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._pydevices = PyDeviceManager()  # manager for python devices
        self._state_cache = PropertyStateCache()  # threadsafe cache for property states
        self._pycore = _CoreDevice(self._state_cache)  # virtual core for python
        self._stop_event: threading.Event = threading.Event()
        self._acquisition_thread: AcquisitionThread | None = None
        self._seq_buffer = SequenceBuffer(size_mb=self._DEFAULT_BUFFER_SIZE_MB)

        super().__init__(*args, **kwargs)

    def _set_current_if_pydevice(self, keyword: Keyword, label: str) -> str:
        """Helper function to set the current core device if it is a python device.

        If the label is a python device, the current device is set and the label is
        cleared (in preparation for calling `super().setDevice()`), otherwise the
        label is returned unchanged.
        """
        if label in self._pydevices:
            self._pycore.set_current(keyword, label)
            label = ""
        elif not label:
            self._pycore.set_current(keyword, None)
        return label

    # -----------------------------------------------------------------------
    # ------------------------ General Core methods  ------------------------
    # -----------------------------------------------------------------------

    def reset(self) -> None:
        with suppress(TimeoutError):
            self.waitForSystem()
        self.unloadAllDevices()
        self._pycore.reset_current()
        super().reset()

    # ------------------------------------------------------------------------
    # ----------------- Functionality for All Devices ------------------------
    # ------------------------------------------------------------------------

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
        return self._pydevices[label].has_property(propName)

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
        if deviceLabel not in self._pydevices:  # pragma: no cover
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
        return self._pydevices[label].get_property_info(propName).type

    def hasPropertyLimits(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().hasPropertyLimits(label, propName)
        with self._pydevices[label] as dev:
            return dev.get_property_info(propName).limits is not None

    def getPropertyLowerLimit(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> float:
        if label not in self._pydevices:  # pragma: no cover
            return super().getPropertyLowerLimit(label, propName)
        with self._pydevices[label] as dev:
            if lims := dev.get_property_info(propName).limits:
                return lims[0]
            return 0

    def getPropertyUpperLimit(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> float:
        if label not in self._pydevices:  # pragma: no cover
            return super().getPropertyUpperLimit(label, propName)
        with self._pydevices[label] as dev:
            if lims := dev.get_property_info(propName).limits:
                return lims[1]
            return 0

    def getAllowedPropertyValues(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> tuple[str, ...]:
        if label not in self._pydevices:  # pragma: no cover
            return super().getAllowedPropertyValues(label, propName)
        with self._pydevices[label] as dev:
            return tuple(dev.get_property_info(propName).allowed_values or ())

    def isPropertyPreInit(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().isPropertyPreInit(label, propName)
        with self._pydevices[label] as dev:
            return dev.get_property_info(propName).is_pre_init

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
            return dev.get_property_info(propName).sequence_max_length

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
            return True  # pragma: no cover

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
        if delayMs != 0:  # pragma: no cover
            raise NotImplementedError("Python devices do not support delays")

    def usesDeviceDelay(self, label: DeviceLabel | str) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().usesDeviceDelay(label)
        return False

    # ########################################################################
    # ---------------------------- XYStageDevice -----------------------------
    # ########################################################################

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

    # ########################################################################
    # ------------------------ Camera Device Methods -------------------------
    # ########################################################################

    # --------------------------------------------------------------------- utils

    def _py_camera(self, cameraLabel: str | None = None) -> Camera | None:
        """Return the *Python* Camera for ``label`` (or current), else ``None``."""
        label = cameraLabel or self.getCameraDevice()
        if label in self._pydevices:
            return self._pydevices.get_device_of_type(label, Camera)
        return None

    def setCameraDevice(self, cameraLabel: DeviceLabel | str) -> None:
        """Set the camera device."""
        label = self._set_current_if_pydevice(KW.CoreCamera, cameraLabel)
        super().setCameraDevice(label)

    def getCameraDevice(self) -> DeviceLabel | Literal[""]:
        """Returns the label of the currently selected camera device.

        Returns empty string if no camera device is selected.
        """
        return self._pycore.current(KW.CoreCamera) or super().getCameraDevice()

    # --------------------------------------------------------------------- snap

    _current_image_buffer: np.ndarray | None = None

    def _do_snap_image(self) -> None:
        if (cam := self._py_camera()) is None:
            return pymmcore.CMMCore.snapImage(self)

        buf = None

        def _get_buffer(shape: Sequence[int], dtype: DTypeLike) -> np.ndarray:
            """Get a buffer for the camera image."""
            nonlocal buf
            buf = np.empty(shape, dtype=dtype)
            return buf

        # synchronous call - consume one item from the generator
        for _ in cam.start_sequence(1, get_buffer=_get_buffer):
            if buf is not None:
                self._current_image_buffer = buf
            else:  # pragma: no cover  #  bad camera implementation
                warnings.warn(
                    "Camera device did not provide an image buffer.",
                    RuntimeWarning,
                    stacklevel=2,
                )
            return

    # --------------------------------------------------------------------- getImage

    @overload
    def getImage(self, *, fix: bool = True) -> np.ndarray: ...
    @overload
    def getImage(self, numChannel: int, *, fix: bool = True) -> np.ndarray: ...

    def getImage(
        self, numChannel: int | None = None, *, fix: bool = True
    ) -> np.ndarray:
        if self._py_camera() is None:  # pragma: no cover
            if numChannel is not None:
                return super().getImage(numChannel, fix=fix)
            return super().getImage(fix=fix)

        if self._current_image_buffer is None:
            raise RuntimeError(
                "No image buffer available. Call snapImage() before calling getImage()."
            )

        return self._current_image_buffer

    # ---------------------------------------------------------------- sequence common

    def _start_sequence(
        self, cam: Camera, n_images: int | None, stop_on_overflow: bool
    ) -> None:
        """Initialise _seq state and call cam.start_sequence."""
        shape, dtype = cam.shape(), np.dtype(cam.dtype())
        camera_label = cam.get_label()

        n_components = shape[2] if len(shape) > 2 else 1
        base_meta: dict[str, Any] = {
            KW.Binning: cam.get_property_value(KW.Binning),
            KW.Metadata_CameraLabel: camera_label,
            KW.Metadata_Height: str(shape[0]),
            KW.Metadata_Width: str(shape[1]),
            KW.Metadata_ROI_X: "0",
            KW.Metadata_ROI_Y: "0",
            KW.PixelType: PixelType.for_bytes(dtype.itemsize, n_components),
        }

        def get_buffer_with_overflow_handling(
            shape: Sequence[int], dtype: DTypeLike
        ) -> np.ndarray:
            try:
                return self._seq_buffer.acquire_slot(shape, dtype)
            except BufferError:
                if not stop_on_overflow:  # we shouldn't get here...
                    raise  # pragma: no cover
                raise BufferOverflowStop() from None

        # Keep track of images acquired for metadata and auto-stop
        counter = count()

        # Create metadata-injecting wrapper for finalize callback
        def finalize_with_metadata(cam_meta: Mapping) -> None:
            img_number = next(counter)
            elapsed_ms = (perf_counter_ns() - start_time) / 1e6
            received = datetime.now().isoformat(sep=" ")
            meta_update = {
                **cam_meta,
                KW.Metadata_TimeInCore: received,
                KW.Metadata_ImageNumber: str(img_number),
                KW.Elapsed_Time_ms: f"{elapsed_ms:.2f}",
            }
            self._seq_buffer.finalize_slot({**base_meta, **meta_update})

            # Auto-stop when we've acquired the requested number of images
            if n_images is not None and (img_number + 1) >= n_images:
                self._stop_event.set()

        # Reset the circular buffer and stop event -------------

        self._stop_event.clear()
        self._seq_buffer.clear()
        self._seq_buffer.overwrite_on_overflow = not stop_on_overflow

        # Create the Acquisition Thread ---------

        self._acquisition_thread = AcquisitionThread(
            image_generator=cam.start_sequence(
                n_images or 2**63 - 1,
                get_buffer_with_overflow_handling,
            ),
            finalize=finalize_with_metadata,
            label=camera_label,
            stop_event=self._stop_event,
        )

        # Zoom zoom ---------

        start_time = perf_counter_ns()
        self._acquisition_thread.start()

    # ------------------------------------------------- startSequenceAcquisition

    def _do_start_sequence_acquisition(
        self, cameraLabel: str, numImages: int, intervalMs: float, stopOnOverflow: bool
    ) -> None:
        if (cam := self._py_camera(cameraLabel)) is None:  # pragma: no cover
            return pymmcore.CMMCore.startSequenceAcquisition(
                self, cameraLabel, numImages, intervalMs, stopOnOverflow
            )

        self._start_sequence(cam, numImages, stopOnOverflow)

    # ------------------------------------------------- continuous acquisition

    def _do_start_continuous_sequence_acquisition(self, intervalMs: float = 0) -> None:
        if (cam := self._py_camera()) is None:  # pragma: no cover
            return pymmcore.CMMCore.startContinuousSequenceAcquisition(self, intervalMs)

        self._start_sequence(cam, None, False)

    # ---------------------------------------------------------------- stopSequence

    def _do_stop_sequence_acquisition(self, cameraLabel: str) -> None:
        if self._py_camera(cameraLabel) is None:  # pragma: no cover
            pymmcore.CMMCore.stopSequenceAcquisition(self, cameraLabel)

        if self._acquisition_thread is not None:
            self._stop_event.set()
            self._acquisition_thread.join()
            self._acquisition_thread = None

    # ------------------------------------------------------------------ queries
    @overload
    def isSequenceRunning(self) -> bool: ...
    @overload
    def isSequenceRunning(self, cameraLabel: DeviceLabel | str) -> bool: ...
    def isSequenceRunning(self, cameraLabel: DeviceLabel | str | None = None) -> bool:
        if self._py_camera(cameraLabel) is None:
            return super().isSequenceRunning()

        if self._acquisition_thread is None:
            return False

        # Check if the thread is actually still alive
        if not self._acquisition_thread.is_alive():
            # Thread has finished, clean it up
            self._acquisition_thread = None
            return False

        return True

    def getRemainingImageCount(self) -> int:
        if self._py_camera() is None:
            return super().getRemainingImageCount()
        return len(self._seq_buffer) if self._seq_buffer is not None else 0

    # ---------------------------------------------------- getImages

    def getLastImage(self) -> np.ndarray:
        if self._py_camera() is None:
            return super().getLastImage()
        if not (self._seq_buffer) or (result := self._seq_buffer.peek_last()) is None:
            raise IndexError("Circular buffer is empty.")
        return result[0]

    @overload
    def getLastImageMD(
        self, channel: int, slice: int, md: pymmcore.Metadata, /
    ) -> np.ndarray: ...
    @overload
    def getLastImageMD(self, md: pymmcore.Metadata, /) -> np.ndarray: ...
    def getLastImageMD(self, *args: Any) -> np.ndarray:
        if self._py_camera() is None:
            return super().getLastImageMD(*args)
        md_object = args[0] if len(args) == 1 else args[-1]
        if not isinstance(md_object, pymmcore.Metadata):  # pragma: no cover
            raise TypeError("Expected a Metadata object for the last argument.")

        if not (self._seq_buffer) or (result := self._seq_buffer.peek_last()) is None:
            raise IndexError("Circular buffer is empty.")

        img, md = result
        for k, v in md.items():
            tag = pymmcore.MetadataSingleTag(k, "_", False)
            tag.SetValue(str(v))
            md_object.SetTag(tag)

        return img

    def getNBeforeLastImageMD(self, n: int, md: pymmcore.Metadata, /) -> np.ndarray:
        if self._py_camera() is None:
            return super().getNBeforeLastImageMD(n, md)

        if (
            not (self._seq_buffer)
            or (result := self._seq_buffer.peek_nth_from_last(n)) is None
        ):
            raise IndexError("Circular buffer is empty or n is out of range.")

        img, md_data = result
        for k, v in md_data.items():
            tag = pymmcore.MetadataSingleTag(k, "_", False)
            tag.SetValue(str(v))
            md.SetTag(tag)

        return img

    # ---------------------------------------------------- popNext

    def _pop_or_raise(self) -> tuple[np.ndarray, Mapping]:
        if not self._seq_buffer or (data := self._seq_buffer.pop_next()) is None:
            raise IndexError("Circular buffer is empty.")
        return data

    def popNextImage(self, *, fix: bool = True) -> np.ndarray:
        if self._py_camera() is None:
            return super().popNextImage(fix=fix)
        return self._pop_or_raise()[0]

    @overload
    def popNextImageMD(
        self, channel: int, slice: int, md: pymmcore.Metadata, /
    ) -> np.ndarray: ...
    @overload
    def popNextImageMD(self, md: pymmcore.Metadata, /) -> np.ndarray: ...
    def popNextImageMD(self, *args: Any) -> np.ndarray:
        if self._py_camera() is None:
            return super().popNextImageMD(*args)

        md_object = args[0] if len(args) == 1 else args[-1]
        if not isinstance(md_object, pymmcore.Metadata):  # pragma: no cover
            raise TypeError("Expected a Metadata object for the last argument.")

        img, md = self._pop_or_raise()
        for k, v in md.items():
            tag = pymmcore.MetadataSingleTag(k, "_", False)
            tag.SetValue(str(v))
            md_object.SetTag(tag)
        return img

    # ---------------------------------------------------------------- circular buffer

    def setCircularBufferMemoryFootprint(self, sizeMB: int) -> None:
        """Set the circular buffer memory footprint in MB."""
        if self._py_camera() is None:
            return super().setCircularBufferMemoryFootprint(sizeMB)

        if sizeMB <= 0:  # pragma: no cover
            raise ValueError("Buffer size must be greater than 0 MB")

        # TODO: what if sequence is running?
        if self.isSequenceRunning():
            self.stopSequenceAcquisition()

        self._seq_buffer = SequenceBuffer(size_mb=sizeMB)

    def initializeCircularBuffer(self) -> None:
        """Initialize the circular buffer."""
        if self._py_camera() is None:
            return super().initializeCircularBuffer()

        self._seq_buffer.clear()

    def getBufferFreeCapacity(self) -> int:
        """Get the number of free slots in the circular buffer."""
        if (cam := self._py_camera()) is None:
            return super().getBufferFreeCapacity()

        if (bytes_per_frame := self._predicted_bytes_per_frame(cam)) <= 0:
            return 0  # pragma: no cover  # Invalid frame size

        if (free_bytes := self._seq_buffer.free_bytes) <= 0:
            return 0

        return free_bytes // bytes_per_frame

    def getBufferTotalCapacity(self) -> int:
        """Get the total capacity of the circular buffer."""
        if (cam := self._py_camera()) is None:
            return super().getBufferTotalCapacity()

        if (bytes_per_frame := self._predicted_bytes_per_frame(cam)) <= 0:
            return 0  # pragma: no cover  # Invalid frame size

        return self._seq_buffer.size_bytes // bytes_per_frame

    def _predicted_bytes_per_frame(self, cam: Camera) -> int:
        # Estimate capacity based on camera settings and circular buffer size
        shape, dtype = cam.shape(), np.dtype(cam.dtype())
        return int(np.prod(shape) * dtype.itemsize)

    def getCircularBufferMemoryFootprint(self) -> int:
        """Get the circular buffer memory footprint in MB."""
        if self._py_camera() is None:
            return super().getCircularBufferMemoryFootprint()

        return int(self._seq_buffer.size_mb)

    def clearCircularBuffer(self) -> None:
        """Clear all images from the circular buffer."""
        if self._py_camera() is None:
            return super().clearCircularBuffer()

        self._seq_buffer.clear()

    def isBufferOverflowed(self) -> bool:
        """Check if the circular buffer has overflowed."""
        if self._py_camera() is None:
            return super().isBufferOverflowed()

        return self._seq_buffer.overflow_occurred

    # ----------------------------------------------------------------- image info

    def getImageBitDepth(self) -> int:
        if (cam := self._py_camera()) is None:  # pragma: no cover
            return super().getImageBitDepth()
        dtype = np.dtype(cam.dtype())
        return dtype.itemsize * 8

    def getBytesPerPixel(self) -> int:
        if (cam := self._py_camera()) is None:  # pragma: no cover
            return super().getBytesPerPixel()
        dtype = np.dtype(cam.dtype())
        return dtype.itemsize

    def getImageBufferSize(self) -> int:
        if (cam := self._py_camera()) is None:  # pragma: no cover
            return super().getImageBufferSize()
        shape, dtype = cam.shape(), np.dtype(cam.dtype())
        return int(np.prod(shape) * dtype.itemsize)

    def getImageHeight(self) -> int:
        if (cam := self._py_camera()) is None:  # pragma: no cover
            return super().getImageHeight()
        return cam.shape()[0]

    def getImageWidth(self) -> int:
        if (cam := self._py_camera()) is None:  # pragma: no cover
            return super().getImageWidth()
        return cam.shape()[1]

    def getNumberOfComponents(self) -> int:
        if (cam := self._py_camera()) is None:  # pragma: no cover
            return super().getNumberOfComponents()
        shape = cam.shape()
        return 1 if len(shape) == 2 else shape[2]

    def getNumberOfCameraChannels(self) -> int:
        if self._py_camera() is None:  # pragma: no cover
            return super().getNumberOfCameraChannels()
        raise NotImplementedError(
            "getNumberOfCameraChannels is not implemented for Python cameras."
        )

    def getCameraChannelName(self, channelNr: int) -> str:
        """Get the name of the camera channel."""
        if self._py_camera() is None:  # pragma: no cover
            return super().getCameraChannelName(channelNr)
        raise NotImplementedError(
            "getCameraChannelName is not implemented for Python cameras."
        )

    @overload
    def getExposure(self) -> float: ...
    @overload
    def getExposure(self, cameraLabel: DeviceLabel | str, /) -> float: ...
    def getExposure(self, cameraLabel: DeviceLabel | str | None = None) -> float:
        """Get the exposure time in milliseconds."""
        if (cam := self._py_camera(cameraLabel)) is None:  # pragma: no cover
            if cameraLabel is None:
                return super().getExposure()
            return super().getExposure(cameraLabel)

        with cam:
            return cam.get_exposure()

    @overload
    def setExposure(self, exp: float, /) -> None: ...
    @overload
    def setExposure(self, cameraLabel: DeviceLabel | str, dExp: float, /) -> None: ...
    def setExposure(self, *args: Any) -> None:
        """Set the exposure time in milliseconds."""
        label, args = _ensure_label(args, min_args=2, getter=self.getCameraDevice)
        if (cam := self._py_camera(label)) is None:  # pragma: no cover
            return super().setExposure(label, *args)
        with cam:
            cam.set_exposure(*args)

    def isExposureSequenceable(self, cameraLabel: DeviceLabel | str) -> bool:
        """Check if the camera supports exposure sequences."""
        if (cam := self._py_camera(cameraLabel)) is None:  # pragma: no cover
            return super().isExposureSequenceable(cameraLabel)
        with cam:
            return cam.is_property_sequenceable(KW.Exposure)

    def loadExposureSequence(
        self, cameraLabel: DeviceLabel | str, exposureSequence_ms: Sequence[float]
    ) -> None:
        """Transfer a sequence of exposure times to the camera."""
        if (cam := self._py_camera(cameraLabel)) is None:  # pragma: no cover
            return super().loadExposureSequence(cameraLabel, exposureSequence_ms)
        with cam:
            cam.load_property_sequence(KW.Exposure, exposureSequence_ms)

    def getExposureSequenceMaxLength(self, cameraLabel: DeviceLabel | str) -> int:
        """Get the maximum length of the exposure sequence."""
        if (cam := self._py_camera(cameraLabel)) is None:  # pragma: no cover
            return super().getExposureSequenceMaxLength(cameraLabel)
        with cam:
            return cam.get_property_info(KW.Exposure).sequence_max_length

    def startExposureSequence(self, cameraLabel: DeviceLabel | str) -> None:
        """Start a sequence of exposures."""
        if (cam := self._py_camera(cameraLabel)) is None:  # pragma: no cover
            return super().startExposureSequence(cameraLabel)
        with cam:
            cam.start_property_sequence(KW.Exposure)

    def stopExposureSequence(self, cameraLabel: DeviceLabel | str) -> None:
        """Stop a sequence of exposures."""
        if (cam := self._py_camera(cameraLabel)) is None:  # pragma: no cover
            return super().stopExposureSequence(cameraLabel)
        with cam:
            cam.stop_property_sequence(KW.Exposure)

    def prepareSequenceAcquisition(self, cameraLabel: DeviceLabel | str) -> None:
        """Prepare the camera for sequence acquisition."""
        if self._py_camera(cameraLabel) is None:  # pragma: no cover
            return super().prepareSequenceAcquisition(cameraLabel)
        # TODO: Implement prepareSequenceAcquisition for Python cameras?

    @overload
    def getPixelSizeAffine(self) -> AffineTuple: ...
    @overload
    def getPixelSizeAffine(self, cached: bool, /) -> AffineTuple: ...
    def getPixelSizeAffine(self, cached: bool = False) -> AffineTuple:
        """Get the pixel size affine transformation matrix."""
        if not (res_id := self.getCurrentPixelSizeConfig(cached)):  # pragma: no cover
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)  # null affine

        cam = self._py_camera()
        if cam is None or (binning := float(cam.get_property_value(KW.Binning))) == 1:
            return tuple(super().getPixelSizeAffine(cached))  # type: ignore

        # in CMMCore, they scale the pixel size affine by the binning factor and mag
        # but they won't pay attention to our camera so we have to reimplement it here
        af = self.getPixelSizeAffineByID(res_id)
        if (factor := binning / self.getMagnificationFactor()) != 1.0:
            af = cast("AffineTuple", tuple(v * factor for v in af))
        return af

    @overload
    def getPixelSizeUm(self) -> float: ...
    @overload
    def getPixelSizeUm(self, cached: bool) -> float: ...
    def getPixelSizeUm(self, cached: bool = False) -> float:
        """Get the pixel size in micrometers."""
        if not (res_id := self.getCurrentPixelSizeConfig(cached)):  # pragma: no cover
            return 0.0

        # in CMMCore, they scale the pixel size by the binning factor and mag
        # but they won't pay attention to our camera so we have to reimplement it here
        cam = self._py_camera()
        if cam is None or (binning := float(cam.get_property_value(KW.Binning))) == 1:
            return super().getPixelSizeUm(cached)

        return self.getPixelSizeUmByID(res_id) * binning / self.getMagnificationFactor()


# Threading ------------------------------------------------------


class AcquisitionThread(threading.Thread):
    """A thread for running sequence acquisition in the background."""

    def __init__(
        self,
        image_generator: Iterator[Mapping],
        finalize: Callable[[Mapping], None],
        label: str,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True)
        self.image_iterator = image_generator
        self.finalize = finalize
        self.label = label
        self.stop_event = stop_event

    def run(self) -> None:
        """Run the sequence and handle the generator pattern."""
        try:
            for metadata in self.image_iterator:
                self.finalize(metadata)
                if self.stop_event.is_set():
                    break
        except BufferOverflowStop:
            # Buffer overflow is a graceful stop condition, not an error
            # this was likely raised by the Unicore above in _start_sequence
            pass
        except BufferError:
            raise  # pragma: no cover
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                f"Error in device {self.label!r} during sequence acquisition: {e}"
            ) from e


# -------------------------------------------------------------------------------


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


class PropertyStateCache(MutableMapping[tuple[str, str], Any]):
    """A thread-safe cache for property states.

    Keys are tuples of (device_label, property_name), and values are the last known
    value of that property.
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], Any] = {}
        self._lock = threading.Lock()

    def __getitem__(self, key: tuple[str, str]) -> Any:
        with self._lock:
            try:
                return self._store[key]
            except KeyError:  # pragma: no cover
                prop, dev = key
                raise KeyError(
                    f"Property {prop!r} of device {dev!r} not found in cache"
                ) from None

    def __setitem__(self, key: tuple[str, str], value: Any) -> None:
        with self._lock:
            self._store[key] = value

    def __delitem__(self, key: tuple[str, str]) -> None:
        with self._lock:
            del self._store[key]

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._store

    def __iter__(self) -> Iterator[tuple[str, str]]:
        with self._lock:
            return iter(self._store.copy())  # Prevent modifications during iteration

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def __repr__(self) -> str:
        with self._lock:
            return f"{self.__class__.__name__}({self._store!r})"
