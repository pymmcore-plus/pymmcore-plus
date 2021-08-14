from enum import IntEnum, auto

# Enums


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

    def __str__(self):
        return self.name.replace("Type", "").replace("Device", "")


class PropertyType(IntEnum):
    Undef = 0
    String = auto()
    Float = auto()
    Integer = auto()

    def to_python(self):
        return {0: None, 1: str, 2: float, 3: int}[self]

    def to_json(self):
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
    """DeviceDetectionStatus from device discovery

    Unimplemented
        there is as yet no mechanism to programmatically detect the device
    Misconfigured
        some information needed to communicate with the device is invalid
    CanNotCommunicate
        communication attributes are valid, but the device does not respond
    CanCommunicate
        communication verified, parameters have been set to valid values.
    """

    Unimplemented = -2
    Misconfigured = -1
    CanNotCommunicate = 0
    CanCommunicate = 1
