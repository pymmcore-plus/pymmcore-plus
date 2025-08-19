from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, overload

from ._constants import DeviceType, FocusDirection, Keyword
from ._property import DeviceProperty
from .events._device_signal_view import _DevicePropValueSignal

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pymmcore import StateLabel
    from typing_extensions import Self

    from pymmcore_plus._accumulator import (
        PositionChangeAccumulator,
        XYPositionChangeAccumulator,
    )
    from pymmcore_plus.core.events._protocol import PSignalInstance

    from ._constants import DeviceDetectionStatus
    from ._mmcore_plus import CMMCorePlus, DeviceSchema


class Device:
    """Convenience object-oriented device API.

    This is the type of object that is returned by
    [`pymmcore_plus.CMMCorePlus.getDeviceObject`][]

    Parameters
    ----------
    device_label : str
        Device label assigned to this device.
    mmcore : CMMCorePlus
        CMMCorePlus instance that owns this device.

    Examples
    --------
    >>> core = CMMCorePlus()
    >>> device = Device("Camera", core)
    >>> device.isLoaded()
    >>> device.load("NotALib", "DCam")  # useful error
    >>> device.load("DemoCamera", "DCam")
    >>> device.initialize()
    >>> device.load("DemoCamera", "DCam")  # no-op w/ useful warning
    >>> device.properties  # tuple of DeviceProperty objects
    >>> device.description()
    >>> device.isBusy()
    >>> device.wait()
    >>> device.type()
    >>> device.schema()  # JSON schema of device properties
    """

    UNASSIGNED = "__UNASSIGNED__"
    propertyChanged: PSignalInstance

    @classmethod
    def create(cls, device_label: str, mmcore: CMMCorePlus) -> Self:
        sub_cls = cls.get_subclass(device_label, mmcore)
        # make sure it's an error to call this class method on a subclass with
        # a non-matching type
        if issubclass(sub_cls, cls):
            return sub_cls(device_label, mmcore)
        dev_type = mmcore.getDeviceType(device_label).name
        raise TypeError(f"Cannot cast {dev_type} {device_label!r} to {cls}")

    @classmethod
    def get_subclass(cls, device_label: str, mmcore: CMMCorePlus) -> type[Device]:
        dev_type = mmcore.getDeviceType(device_label)
        return _TYPE_MAP[dev_type]

    def __init__(
        self,
        device_label: str = UNASSIGNED,
        mmcore: CMMCorePlus | None = None,
        adapter_name: str = "",
        device_name: str = "",
        type: DeviceType = DeviceType.UnknownType,
        description: str = "",
    ) -> None:
        if mmcore is None:
            from ._mmcore_plus import CMMCorePlus

            self._mmc = CMMCorePlus.instance()
        else:
            self._mmc = mmcore

        self._label = device_label
        self._type = None
        if self.isLoaded():
            adapter_name = self._mmc.getDeviceLibrary(device_label)
            device_name = self._mmc.getDeviceName(device_label)
            description = self._mmc.getDeviceDescription(device_label)
            type = self._mmc.getDeviceType(device_label)  # noqa: A001
            if self.type() != type:
                raise TypeError(
                    f"Cannot create loaded device with label {device_label!r} and type "
                    f"{type.name!r} as an instance of {self.__class__.__name__!r}"
                )

        self._adapter_name = adapter_name
        self._device_name = device_name
        self._type = type
        self._description = description
        self.propertyChanged = _DevicePropValueSignal(device_label, None, self._mmc)

    @property
    def label(self) -> str:
        """Return the assigned label of this device."""
        return self._label

    @label.setter
    def label(self, value: str) -> None:
        if self.isLoaded():
            raise RuntimeError(f"Cannot change label of loaded device {self.label!r}.")
        if value in self._mmc.getLoadedDevices():  # pragma: no cover
            raise RuntimeError(f"Label {value!r} is already in use.")
        self._label = value

    @property
    def core(self) -> CMMCorePlus:
        """Return the `CMMCorePlus` instance to which this Device is bound."""
        return self._mmc

    def isBusy(self) -> bool:
        """Return busy status for this device."""
        return self._mmc.deviceBusy(self.label)

    def delayMs(self) -> float:
        """Return action delay in ms for this device."""
        return self._mmc.getDeviceDelayMs(self.label)

    def setDelayMs(self, delayMs: float) -> None:
        """Override the built-in value for the action delay."""
        self._mmc.setDeviceDelayMs(self.label, delayMs)

    def usesDelay(self) -> bool:
        """Return `True` if the device will use the delay setting or not."""
        return self._mmc.usesDeviceDelay(self.label)

    def description(self) -> str:
        """Return device description."""
        return self._description or self._mmc.getDeviceDescription(self.label)

    def library(self) -> str:
        """Return device library (aka module, device adapter) name."""
        return self._adapter_name or self._mmc.getDeviceLibrary(self.label)

    def name(self) -> str:
        """Return the device name (this is not the same as the assigned label)."""
        return self._device_name or self._mmc.getDeviceName(self.label)

    def propertyNames(self) -> tuple[str, ...]:
        """Return all property names supported by this device."""
        return self._mmc.getDevicePropertyNames(self.label)

    @property
    def properties(self) -> tuple[DeviceProperty, ...]:
        """Get all properties supported by device as DeviceProperty objects."""
        return tuple(self.getPropertyObject(name) for name in self.propertyNames())

    def getPropertyObject(self, property_name: str) -> DeviceProperty:
        """Return a `DeviceProperty` object bound to this device on this core."""
        if not self._mmc.hasProperty(self.label, property_name):
            raise ValueError(f"Device {self.label!r} has no property {property_name!r}")
        return DeviceProperty(self.label, property_name, self._mmc)

    def setProperty(self, property_name: str, value: bool | float | int | str) -> None:
        """Set a device property value.

        See also,
        [`Device.getPropertyObject`][pymmcore_plus.core.Device.getPropertyObject].

        Examples
        --------
        >>> camera = Device("Camera")
        >>> camera.setProperty("Exposure", 100)
        >>> print(camera.getProperty("Exposure"))
        # or
        >>> exposure = camera.getPropertyObject("Exposure")
        >>> exposure.value = 100
        >>> print(exposure.value)
        """
        return self._mmc.setProperty(self.label, property_name, value)

    def getProperty(self, property_name: str) -> str:
        """Get a device property value."""
        return self._mmc.getProperty(self.label, property_name)

    def initialize(self) -> None:
        """Initialize device."""
        return self._mmc.initializeDevice(self.label)

    def unload(self) -> None:
        """Unload device from the core and adjust all configuration data."""
        return self._mmc.unloadDevice(self.label)

    def isLoaded(self) -> bool:
        """Return `True` if device is loaded."""
        return self.label in self._mmc.getLoadedDevices()

    def load(
        self,
        adapter_name: str = "",
        device_name: str = "",
        device_label: str = "",
    ) -> Device:
        """Load device from the plugin library.

        Parameters
        ----------
        adapter_name : str
            The name of the device adapter module (short name, not full file name).
            (This is what is returned by `Device.library()`). Must be specified if
            `adapter_name` was not provided to the `Device` constructor.
        device_name : str
            The name of the device. The name must correspond to one of the names
            recognized by the specific plugin library. (This is what is returned by
            `Device.name()`). Must be specified if `device_name` was not provided to
            the `Device` constructor.
        device_label : str
            The name to assign to the device. If not specified, the device will be
            assigned a default name: `adapter_name-device_name`, unless this Device
            instance was initialized with a label.
        """
        # if self.isLoaded():
        # raise RuntimeError(f"Device {self.label!r} is already loaded.")

        if not (adapter_name := adapter_name or self._adapter_name):
            raise TypeError("Must specify adapter_name")
        if not (device_name := device_name or self._device_name):
            raise TypeError("Must specify device_name")
        if device_label:
            self.label = device_label
        elif self.label == self.UNASSIGNED:
            self.label = f"{adapter_name}-{device_name}"

        # note: this method takes care of label already being loaded and only
        # warns if the exact label, adapter, and device are in use
        self._mmc.loadDevice(self.label, adapter_name, device_name)
        return Device.create(self.label, self._mmc)

    def detect(self) -> DeviceDetectionStatus:
        """Tries to communicate to device through a given serial port.

        Used to automate discovery of correct serial port. Also configures the
        serial port correctly.
        """
        return self._mmc.detectDevice(self.label)

    def supportsDetection(self) -> bool:
        """Return whether or not the device supports automatic device detection.

        (i.e. whether or not detectDevice() may be safely called).
        """
        try:
            return self._mmc.supportsDeviceDetection(self.label)
        except RuntimeError:
            return False  # e.g. core devices

    def type(self) -> DeviceType:
        """Return device type."""
        return self._type or self._mmc.getDeviceType(self.label)

    def schema(self) -> DeviceSchema:
        """Return dict in JSON-schema format for properties of `device_label`."""
        return self._mmc.getDeviceSchema(self.label)

    def wait(self) -> None:
        """Block the calling thread until device becomes non-busy."""
        self._mmc.waitForDevice(self.label)

    def getParentLabel(self) -> str:
        """Return the parent device label of this device."""
        return self._mmc.getParentLabel(self.label)

    def setParentLabel(self, parent_label: str) -> None:
        """Set the parent device label of this device."""
        self._mmc.setParentLabel(self.label, parent_label)

    def __repr__(self) -> str:
        if self.isLoaded():
            n = len(self.propertyNames())
            props = f"{n} {'properties' if n > 1 else 'property'}"
            lib = f"({self.library()}::{self.name()}) "
        else:
            props = "NOT LOADED"
            lib = ""
        core = repr(self._mmc).strip("<>")
        return f"<{self.__class__.__name__} {self.label!r} {lib}on {core}: {props}>"


class CameraDevice(Device):
    def type(self) -> Literal[DeviceType.Camera]:
        return DeviceType.Camera

    def setROI(self, x: int, y: int, width: int, height: int) -> None:
        """Set region of interest for camera."""
        self._mmc.setROI(self.label, x, y, width, height)

    def getROI(self) -> list[int]:  # always a list of 4 ints ... but not a tuple
        """Return region of interest for camera."""
        return self._mmc.getROI(self.label)

    # no device label-specific method for these ... would need to implement directly
    # clearROI
    # isMultiROISupported
    # isMultiROIEnabled
    # setMultiROI
    # getMultiROI
    # snapImage
    # getImage
    # getImageWidth
    # getImageHeight
    # getBytesPerPixel
    # getImageBitDepth
    # getNumberOfComponents
    # getNumberOfCameraChannels

    @property
    def exposure(self) -> float:
        return self.getExposure()

    @exposure.setter
    def exposure(self, value: float) -> None:
        self.setExposure(value)

    def setExposure(self, exposure: float) -> None:
        """Set exposure time for camera."""
        self._mmc.setExposure(self.label, exposure)

    def getExposure(self) -> float:
        """Return exposure time for camera."""
        return self._mmc.getExposure(self.label)

    def startSequenceAcquisition(
        self, numImages: int, intervalMs: float, stopOnOverflow: bool
    ) -> None:
        """Start sequence acquisition."""
        self._mmc.startSequenceAcquisition(
            self.label, numImages, intervalMs, stopOnOverflow
        )

    def prepareSequenceAcquisition(self) -> None:
        """Prepare sequence acquisition."""
        self._mmc.prepareSequenceAcquisition(self.label)

    def stopSequenceAcquisition(self) -> None:
        """Stop sequence acquisition."""
        self._mmc.stopSequenceAcquisition(self.label)

    def isSequenceRunning(self) -> bool:
        """Return `True` if sequence acquisition is running."""
        return self._mmc.isSequenceRunning(self.label)

    def isExposureSequenceable(self) -> bool:
        """Return `True` if camera supports exposure sequence."""
        return self._mmc.isExposureSequenceable(self.label)

    def loadExposureSequence(self, sequence: Sequence[float]) -> None:
        """Load exposure sequence."""
        self._mmc.loadExposureSequence(self.label, sequence)

    def startExposureSequence(self) -> None:
        """Start exposure sequence."""
        self._mmc.startExposureSequence(self.label)

    def stopExposureSequence(self) -> None:
        """Stop exposure sequence."""
        self._mmc.stopExposureSequence(self.label)

    def getExposureSequenceMaxLength(self) -> int:
        """Return the maximum length of a camera's exposure sequence."""
        return self._mmc.getExposureSequenceMaxLength(self.label)

    isSequenceable = isExposureSequenceable
    loadSequence = loadExposureSequence
    startSequence = startExposureSequence
    stopSequence = stopExposureSequence
    getSequenceMaxLength = getExposureSequenceMaxLength


class ShutterDevice(Device):
    def type(self) -> Literal[DeviceType.Shutter]:
        return DeviceType.Shutter

    def open(self) -> None:
        """Open shutter."""
        self._mmc.setShutterOpen(self.label, True)

    def close(self) -> None:
        """Close shutter."""
        self._mmc.setShutterOpen(self.label, False)

    def isOpen(self) -> bool:
        """Return `True` if shutter is open."""
        return self._mmc.getShutterOpen(self.label)


class StateDevice(Device):
    def type(self) -> Literal[DeviceType.State]:
        return DeviceType.State

    @property
    def state(self) -> int:
        return self._mmc.getState(self.label)

    @state.setter
    def state(self, state: int) -> None:
        self._mmc.setState(self.label, state)

    def setState(self, state: int) -> None:
        """Set state."""
        self._mmc.setState(self.label, state)

    def getState(self) -> int:
        """Return state."""
        return self._mmc.getState(self.label)

    def getNumberOfStates(self) -> int:
        """Return number of states."""
        return self._mmc.getNumberOfStates(self.label)

    def setStateLabel(self, label: str) -> None:
        """Set state by label."""
        self._mmc.setStateLabel(self.label, label)

    def getStateLabel(self) -> StateLabel:
        """Return state label."""
        return self._mmc.getStateLabel(self.label)

    def defineStateLabel(self, state: int, label: str) -> None:
        """Define state labels."""
        self._mmc.defineStateLabel(self.label, state, label)

    def getStateLabels(self) -> tuple[StateLabel, ...]:
        """Return state labels."""
        return self._mmc.getStateLabels(self.label)

    def getStateFromLabel(self, label: str) -> int:
        """Return state for given label."""
        return self._mmc.getStateFromLabel(self.label, label)


class _StageBase(Device):
    def stop(self) -> None:
        """Stop XY stage movement."""
        self._mmc.stop(self.label)

    def home(self) -> None:
        """Home XY stage."""
        self._mmc.home(self.label)


class StageDevice(_StageBase):
    def type(self) -> Literal[DeviceType.Stage]:
        return DeviceType.Stage

    def setPosition(self, position: float) -> None:
        self._mmc.setPosition(self.label, position)

    def getPosition(self) -> float:
        return self._mmc.getPosition(self.label)

    @property
    def position(self) -> float:
        return self.getPosition()

    @position.setter
    def position(self, value: float) -> None:
        self.setPosition(value)

    def setRelativePosition(self, offset: float) -> None:
        self._mmc.setRelativePosition(self.label, offset)

    def getPositionAccumulator(self) -> PositionChangeAccumulator:
        from pymmcore_plus._accumulator import PositionChangeAccumulator

        return PositionChangeAccumulator.get_cached(self.label, self._mmc)

    def setOrigin(self) -> None:
        self._mmc.setOrigin(self.label)

    def setAdapterOrigin(self, newZUm: float) -> None:
        self._mmc.setAdapterOrigin(self.label, newZUm)

    def setFocusDirection(self, sign: int) -> None:
        self._mmc.setFocusDirection(self.label, sign)

    def getFocusDirection(self) -> FocusDirection:
        return self._mmc.getFocusDirection(self.label)

    def isContinuousFocusDrive(self) -> bool:
        """Return `True` if device supports continuous focus."""
        return self._mmc.isContinuousFocusDrive(self.label)

    def isStageSequenceable(self) -> bool:
        """Return `True` if device supports stage sequence."""
        return self._mmc.isStageSequenceable(self.label)

    def isStageLinearSequenceable(self) -> bool:
        """Return `True` if device supports linear stage sequence."""
        return self._mmc.isStageLinearSequenceable(self.label)

    def startStageSequence(self) -> None:
        """Start stage sequence."""
        self._mmc.startStageSequence(self.label)

    def stopStageSequence(self) -> None:
        """Stop stage sequence."""
        self._mmc.stopStageSequence(self.label)

    def getStageSequenceMaxLength(self) -> int:
        """Return maximum length of stage sequence."""
        return self._mmc.getStageSequenceMaxLength(self.label)

    def loadStageSequence(self, positions: Sequence[float]) -> None:
        """Load stage sequence."""
        self._mmc.loadStageSequence(self.label, positions)

    def setStageLinearSequence(self, dZ_um: float, nSlices: int) -> None:
        """Set stage linear sequence."""
        self._mmc.setStageLinearSequence(self.label, dZ_um, nSlices)

    isSequenceable = isStageSequenceable
    loadSequence = loadStageSequence
    startSequence = startStageSequence
    stopSequence = stopStageSequence
    getSequenceMaxLength = getStageSequenceMaxLength


class XYStageDevice(_StageBase):
    def type(self) -> Literal[DeviceType.XYStage]:
        return DeviceType.XYStage

    def setXYPosition(self, x: float, y: float) -> None:
        """Set the position of the XY stage in microns."""
        self._mmc.setXYPosition(self.label, x, y)

    def getXYPosition(self) -> Sequence[float]:
        """Return the position of the XY stage in microns."""
        return self._mmc.getXYPosition(self.label)

    @property
    def position(self) -> tuple[float, float]:
        """Return the position of the XY stage in microns."""
        return tuple(self._mmc.getXYPosition(self.label))  # type: ignore [return-value]

    @position.setter
    def position(self, value: tuple[float, float]) -> None:
        """Set the position of the XY stage in microns."""
        self._mmc.setXYPosition(self.label, *value)

    def setRelativeXYPosition(self, dx: float, dy: float) -> None:
        """Set the relative position of the XY stage in microns."""
        self._mmc.setRelativeXYPosition(self.label, dx, dy)

    def getPositionAccumulator(self) -> XYPositionChangeAccumulator:
        from pymmcore_plus._accumulator import XYPositionChangeAccumulator

        return XYPositionChangeAccumulator.get_cached(self.label, self._mmc)

    def getXPosition(self) -> float:
        """Return the X position of the XY stage in microns."""
        return self._mmc.getXPosition(self.label)

    def getYPosition(self) -> float:
        """Return the Y position of the XY stage in microns."""
        return self._mmc.getYPosition(self.label)

    def setOriginXY(self) -> None:
        """Zero the current XY stage's coordinates at the current position."""
        self._mmc.setOriginXY(self.label)

    setOrigin = setOriginXY

    def setOriginX(self) -> None:
        """Zero the given XY stage's X coordinate at the current position."""
        self._mmc.setOriginX(self.label)

    def setOriginY(self) -> None:
        """Zero the given XY stage's Y coordinate at the current position."""
        self._mmc.setOriginY(self.label)

    def setAdapterOriginXY(self, newXUm: float, newYUm: float) -> None:
        """Enable software translation of coordinates for the current XY stage.

        The current position of the stage becomes (newXUm, newYUm). It is recommended
        that setOriginXY() be used instead where available.
        """
        self._mmc.setAdapterOriginXY(self.label, newXUm, newYUm)

    def isXYStageSequenceable(self) -> bool:
        """Return `True` if device supports XY stage sequence."""
        return self._mmc.isXYStageSequenceable(self.label)

    def startXYStageSequence(self) -> None:
        """Start XY stage sequence."""
        self._mmc.startXYStageSequence(self.label)

    def stopXYStageSequence(self) -> None:
        """Stop XY stage sequence."""
        self._mmc.stopXYStageSequence(self.label)

    def getXYStageSequenceMaxLength(self) -> int:
        """Return maximum length of XY stage sequence."""
        return self._mmc.getXYStageSequenceMaxLength(self.label)

    def loadXYStageSequence(
        self, xSequence: Sequence[float], ySequence: Sequence[float]
    ) -> None:
        """Load XY stage sequence."""
        self._mmc.loadXYStageSequence(self.label, xSequence, ySequence)

    def loadSequence(self, sequence: Sequence[tuple[float, float]]) -> None:
        """Load XY stage sequence with a sequence of 2-tuples.

        Provided as a wrapper for loadXYStageSequence, for API parity with other
        sequencaable devices.
        """
        xSequence, ySequence = zip(*sequence)
        self._mmc.loadXYStageSequence(self.label, xSequence, ySequence)

    isSequenceable = isXYStageSequenceable
    startSequence = startXYStageSequence
    stopSequence = stopXYStageSequence
    getSequenceMaxLength = getXYStageSequenceMaxLength


class SerialDevice(Device):
    def type(self) -> Literal[DeviceType.Serial]:
        return DeviceType.Serial

    def setCommand(self, command: str, term: str) -> None:
        """Send string to the serial device and return an answer."""
        self._mmc.setSerialPortCommand(self.label, command, term)

    def getAnswer(self, term: str) -> str:
        """Continuously read from the serial port until the term is encountered."""
        return self._mmc.getSerialPortAnswer(self.label, term)

    def write(self, data: bytes) -> None:
        """Send string to the serial device."""
        self._mmc.writeToSerialPort(self.label, data)

    def read(self) -> list[str]:
        """Reads the contents of the Rx buffer."""
        return self._mmc.readFromSerialPort(self.label)

    def setProperties(
        self,
        answerTimeout: str,
        baudRate: str,
        delayBetweenCharsMs: str,
        handshaking: str,
        parity: str,
        stopBits: str,
    ) -> None:
        """Sets all com port properties in a single call."""
        self._mmc.setSerialProperties(
            self.label,
            answerTimeout,
            baudRate,
            delayBetweenCharsMs,
            handshaking,
            parity,
            stopBits,
        )

    @property
    def answer_timeout(self) -> str:
        """Return the timeout for serial port commands."""
        return self._mmc.getProperty(self.label, Keyword.AnswerTimeout)

    @property
    def baud_rate(self) -> str:
        """Return the baud rate for serial port commands."""
        return self._mmc.getProperty(self.label, Keyword.BaudRate)

    @property
    def data_bits(self) -> str:
        """Return the data bits for serial port commands."""
        return self._mmc.getProperty(self.label, Keyword.DataBits)

    @property
    def parity(self) -> str:
        """Return the parity for serial port commands."""
        return self._mmc.getProperty(self.label, Keyword.Parity)

    @property
    def stop_bits(self) -> str:
        """Return the stop bits for serial port commands."""
        return self._mmc.getProperty(self.label, Keyword.StopBits)

    @property
    def handshaking(self) -> str:
        """Return the handshaking for serial port commands."""
        return self._mmc.getProperty(self.label, Keyword.Handshaking)

    @property
    def delay_between_chars_ms(self) -> str:
        """Return the delay between characters in milliseconds."""
        return self._mmc.getProperty(self.label, Keyword.DelayBetweenCharsMs)


class GenericDevice(Device):
    def type(self) -> Literal[DeviceType.Generic]:
        return DeviceType.Generic


class AutoFocusDevice(Device):
    def type(self) -> Literal[DeviceType.AutoFocus]:
        return DeviceType.AutoFocus

    # none of these actually accept a label, and should be called on Core
    # getLastFocusScore
    # getCurrentFocusScore
    # enableContinuousFocus
    # isContinuousFocusEnabled
    # isContinuousFocusLocked
    # isContinuousFocusDrive
    # fullFocus
    # incrementalFocus
    # setAutoFocusOffset
    # getAutoFocusOffset


class SLMDevice(Device):
    def type(self) -> Literal[DeviceType.SLM]:
        return DeviceType.SLM

    def setImage(self, pixels: Any) -> None:
        """Write an image to the SLM ."""
        self._mmc.setSLMImage(self.label, pixels)

    @overload
    def setPixelsTo(self, intensity: int, /) -> None: ...
    @overload
    def setPixelsTo(self, red: int, green: int, blue: int, /) -> None: ...
    def setPixelsTo(self, *args: int) -> None:
        """Set all SLM pixels to a single 8-bit intensity or RGB color."""
        self._mmc.setSLMPixelsTo(self.label, *args)

    def displayImage(self) -> None:
        """Display the image on the SLM."""
        self._mmc.displaySLMImage(self.label)

    def setExposure(self, exposure_ms: float) -> None:
        """Set exposure time for SLM."""
        self._mmc.setSLMExposure(self.label, exposure_ms)

    def getExposure(self) -> float:
        """Return exposure time for SLM."""
        return self._mmc.getSLMExposure(self.label)

    @property
    def exposure(self) -> float:
        return self.getExposure()

    @exposure.setter
    def exposure(self, value: float) -> None:
        self.setExposure(value)

    def width(self) -> int:
        """Return the width of the SLM image."""
        return self._mmc.getSLMWidth(self.label)

    def height(self) -> int:
        """Return the height of the SLM image."""
        return self._mmc.getSLMHeight(self.label)

    def numberOfComponents(self) -> int:
        """Return the number of components in the SLM image."""
        return self._mmc.getSLMNumberOfComponents(self.label)

    def bytesPerPixel(self) -> int:
        """Return the number of bytes per pixel in the SLM image."""
        return self._mmc.getSLMBytesPerPixel(self.label)

    def getSequenceMaxLength(self) -> int:
        """Return the maximum length of a sequence for the SLM."""
        return self._mmc.getSLMSequenceMaxLength(self.label)

    def isSequenceable(self) -> bool:
        """Return `True` if the SLM supports sequences."""
        # there is no MMCore API for this
        try:
            return self.getSequenceMaxLength() > 0
        except RuntimeError:
            return False

    def loadSequence(self, imageSequence: list[bytes]) -> None:
        """Load a sequence of images to the SLM."""
        self._mmc.loadSLMSequence(self.label, imageSequence)

    def startSequence(self) -> None:
        """Start the sequence of images on the SLM."""
        self._mmc.startSLMSequence(self.label)

    def stopSequence(self) -> None:
        """Stop the sequence of images on the SLM."""
        self._mmc.stopSLMSequence(self.label)


class HubDevice(Device):
    def type(self) -> Literal[DeviceType.Hub]:
        return DeviceType.Hub

    def getInstalledDevices(self) -> tuple[str, ...]:
        """Return the list of installed devices."""
        return self._mmc.getInstalledDevices(self.label)

    def getInstalledDeviceDescription(self, device_label: str) -> str:
        """Return the description of the installed device."""
        return self._mmc.getInstalledDeviceDescription(self.label, device_label)

    def getLoadedPeripheralDevices(self) -> tuple[str, ...]:
        """Return the list of loaded peripheral devices."""
        return self._mmc.getLoadedPeripheralDevices(self.label)


class GalvoDevice(Device):
    def type(self) -> Literal[DeviceType.Galvo]:
        return DeviceType.Galvo

    def pointAndFire(self, x: float, y: float, pulseTime_us: float) -> None:
        """Set Galvo to (x, y) and fire the laser for a predetermined duration."""
        self._mmc.pointGalvoAndFire(self.label, x, y, pulseTime_us)

    def setSpotInterval(self, pulseTime_us: float) -> None:
        """Set the SpotInterval for the specified galvo device."""
        self._mmc.setGalvoSpotInterval(self.label, pulseTime_us)

    def setPosition(self, x: float, y: float) -> None:
        """Set the position of the galvo device."""
        self._mmc.setGalvoPosition(self.label, x, y)

    def getPosition(self) -> list[float]:
        """Return the position of the galvo device."""
        return self._mmc.getGalvoPosition(self.label)

    @property
    def position(self) -> list[float]:
        return self._mmc.getGalvoPosition(self.label)

    @position.setter
    def position(self, value: tuple[float, float]) -> None:
        self._mmc.setGalvoPosition(self.label, *value)

    def setIlluminationState(self, state: bool) -> None:
        """Set the galvo's illumination state to on or off."""
        self._mmc.setGalvoIlluminationState(self.label, state)

    def getXRange(self) -> float:
        """Get the Galvo x range."""
        return self._mmc.getGalvoXRange(self.label)

    def getXMinimum(self) -> float:
        """Get the Galvo x minimum."""
        return self._mmc.getGalvoXMinimum(self.label)

    def getYRange(self) -> float:
        """Get the Galvo y range."""
        return self._mmc.getGalvoYRange(self.label)

    def getYMinimum(self) -> float:
        """Get the Galvo y minimum."""
        return self._mmc.getGalvoYMinimum(self.label)

    def addPolygonVertex(self, polygonIndex: int, x: float, y: float) -> None:
        """Add a vertex to the polygon."""
        self._mmc.addGalvoPolygonVertex(self.label, polygonIndex, x, y)

    def deletePolygons(self) -> None:
        """Delete all polygons."""
        self._mmc.deleteGalvoPolygons(self.label)

    def loadPolygons(self) -> None:
        """Load a set of galvo polygons to the device."""
        self._mmc.loadGalvoPolygons(self.label)

    def runPolygons(self) -> None:
        """Run a loop of galvo polygons."""
        self._mmc.runGalvoPolygons(self.label)

    def runSequence(self) -> None:
        """Run a sequence of galvo positions."""
        self._mmc.runGalvoSequence(self.label)

    def setPolygonRepetitions(self, repetitions: int) -> None:
        """Set the number of times the galvo polygon should be repeated."""
        self._mmc.setGalvoPolygonRepetitions(self.label, repetitions)

    def getChannel(self) -> str:
        """Get the name of the active galvo channel (for a multi-laser galvo device)."""
        return self._mmc.getGalvoChannel(self.label)


class ImageProcessorDevice(Device):
    def type(self) -> Literal[DeviceType.ImageProcessor]:
        return DeviceType.ImageProcessor


class SignalIODevice(Device):
    def type(self) -> Literal[DeviceType.SignalIO]:
        return DeviceType.SignalIO


class MagnifierDevice(Device):
    def type(self) -> Literal[DeviceType.Magnifier]:
        return DeviceType.Magnifier


# Special device...
class CoreDevice(Device):
    def type(self) -> Literal[DeviceType.Core]:
        return DeviceType.Core


_TYPE_MAP: dict[DeviceType, type[Device]] = {
    DeviceType.Camera: CameraDevice,
    DeviceType.Shutter: ShutterDevice,
    DeviceType.State: StateDevice,
    DeviceType.Stage: StageDevice,
    DeviceType.XYStage: XYStageDevice,
    DeviceType.Serial: SerialDevice,
    DeviceType.Generic: GenericDevice,
    DeviceType.AutoFocus: AutoFocusDevice,
    DeviceType.Core: CoreDevice,
    DeviceType.ImageProcessor: ImageProcessorDevice,
    DeviceType.SignalIO: SignalIODevice,
    DeviceType.Magnifier: MagnifierDevice,
    DeviceType.SLM: SLMDevice,
    DeviceType.Hub: HubDevice,
    DeviceType.Galvo: GalvoDevice,
}
