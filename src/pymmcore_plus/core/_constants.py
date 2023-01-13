from __future__ import annotations

from enum import IntEnum, auto


class DeviceType(IntEnum):
    UnknownType = 0
    AnyType = auto()
    CameraDevice = auto()
    ShutterDevice = auto()
    StateDevice = auto()
    StageDevice = auto()
    XYStageDevice = auto()
    SerialDevice = auto()
    GenericDevice = auto()
    AutoFocusDevice = auto()
    CoreDevice = auto()
    ImageProcessorDevice = auto()
    SignalIODevice = auto()
    MagnifierDevice = auto()
    SLMDevice = auto()
    HubDevice = auto()
    GalvoDevice = auto()
    # aliases for clearer naming (e.g. `DeviceType.Camera`)
    Unknown = UnknownType
    Any = AnyType
    Camera = CameraDevice
    Shutter = ShutterDevice
    State = StateDevice
    Stage = StageDevice
    XYStage = XYStageDevice
    Serial = SerialDevice
    Generic = GenericDevice
    AutoFocus = AutoFocusDevice
    Core = CoreDevice
    ImageProcessor = ImageProcessorDevice
    SignalIO = SignalIODevice
    Magnifier = MagnifierDevice
    SLM = SLMDevice
    Hub = HubDevice
    Galvo = GalvoDevice

    def __str__(self) -> str:
        return str(self.name).replace("Type", "").replace("Device", "")


class PropertyType(IntEnum):
    Undef = 0
    String = auto()
    Float = auto()
    Integer = auto()

    def to_python(self) -> type | None:
        return {0: None, 1: str, 2: float, 3: int}[self]

    def to_json(self) -> str:
        return {0: "null", 1: "string", 2: "number", 3: "integer"}[self]


class ActionType(IntEnum):
    NoAction = 0
    BeforeGet = auto()
    AfterSet = auto()
    IsSequenceable = auto()
    AfterLoadSequence = auto()
    StartSequence = auto()
    StopSequence = auto()


class PortType(IntEnum):
    InvalidPort = 0
    SerialPort = auto()
    USBPort = auto()
    HIDPort = auto()


class FocusDirection(IntEnum):
    FocusDirectionUnknown = 0
    FocusDirectionTowardSample = auto()
    FocusDirectionAwayFromSample = auto()
    # aliases
    Unknown = FocusDirectionUnknown
    TowardSample = FocusDirectionTowardSample
    AwayFromSample = FocusDirectionAwayFromSample


class DeviceNotification(IntEnum):
    Attention = 0
    Done = auto()
    StatusChanged = auto()


class DeviceDetectionStatus(IntEnum):
    """DeviceDetectionStatus from device discovery."""

    Unimplemented = -2
    """There is as yet no mechanism to programmatically detect the device."""
    Misconfigured = -1
    """Some information needed to communicate with the device is invalid."""
    CanNotCommunicate = 0
    """Communication attributes are valid, but the device does not respond."""
    CanCommunicate = 1
    """Communication verified, parameters have been set to valid values."""
