from __future__ import annotations

from enum import Enum, IntEnum

import pymmcore

# NOTE: by using pymmcore.attributes, we guarantee that the values are the same
# however, we also risk AttributeErrors in the future.
# we could do this dynamically, but then we lose IDE type hints


class Keyword(str, Enum):
    Name = pymmcore.g_Keyword_Name
    Description = pymmcore.g_Keyword_Description
    CameraName = pymmcore.g_Keyword_CameraName
    CameraID = pymmcore.g_Keyword_CameraID
    CameraChannelName = pymmcore.g_Keyword_CameraChannelName
    CameraChannelIndex = pymmcore.g_Keyword_CameraChannelIndex
    Binning = pymmcore.g_Keyword_Binning
    Exposure = pymmcore.g_Keyword_Exposure
    ActualExposure = pymmcore.g_Keyword_ActualExposure
    ActualInterval_ms = pymmcore.g_Keyword_ActualInterval_ms
    Interval_ms = pymmcore.g_Keyword_Interval_ms
    Elapsed_Time_ms = pymmcore.g_Keyword_Elapsed_Time_ms
    PixelType = pymmcore.g_Keyword_PixelType
    ReadoutTime = pymmcore.g_Keyword_ReadoutTime
    ReadoutMode = pymmcore.g_Keyword_ReadoutMode
    Gain = pymmcore.g_Keyword_Gain
    EMGain = pymmcore.g_Keyword_EMGain
    Offset = pymmcore.g_Keyword_Offset
    CCDTemperature = pymmcore.g_Keyword_CCDTemperature
    CCDTemperatureSetPoint = pymmcore.g_Keyword_CCDTemperatureSetPoint
    State = pymmcore.g_Keyword_State
    Label = pymmcore.g_Keyword_Label
    Position = pymmcore.g_Keyword_Position
    Type = pymmcore.g_Keyword_Type
    Delay = pymmcore.g_Keyword_Delay
    BaudRate = pymmcore.g_Keyword_BaudRate
    DataBits = pymmcore.g_Keyword_DataBits
    StopBits = pymmcore.g_Keyword_StopBits
    Parity = pymmcore.g_Keyword_Parity
    Handshaking = pymmcore.g_Keyword_Handshaking
    DelayBetweenCharsMs = pymmcore.g_Keyword_DelayBetweenCharsMs
    Port = pymmcore.g_Keyword_Port
    AnswerTimeout = pymmcore.g_Keyword_AnswerTimeout
    Speed = pymmcore.g_Keyword_Speed
    CoreDevice = pymmcore.g_Keyword_CoreDevice
    CoreInitialize = pymmcore.g_Keyword_CoreInitialize
    CoreCamera = pymmcore.g_Keyword_CoreCamera
    CoreShutter = pymmcore.g_Keyword_CoreShutter
    CoreXYStage = pymmcore.g_Keyword_CoreXYStage
    CoreFocus = pymmcore.g_Keyword_CoreFocus
    CoreAutoFocus = pymmcore.g_Keyword_CoreAutoFocus
    CoreAutoShutter = pymmcore.g_Keyword_CoreAutoShutter
    CoreChannelGroup = pymmcore.g_Keyword_CoreChannelGroup
    CoreImageProcessor = pymmcore.g_Keyword_CoreImageProcessor
    CoreSLM = pymmcore.g_Keyword_CoreSLM
    CoreGalvo = pymmcore.g_Keyword_CoreGalvo
    CoreTimeoutMs = pymmcore.g_Keyword_CoreTimeoutMs
    Channel = pymmcore.g_Keyword_Channel
    Version = pymmcore.g_Keyword_Version
    ColorMode = pymmcore.g_Keyword_ColorMode
    Transpose_SwapXY = pymmcore.g_Keyword_Transpose_SwapXY
    Transpose_MirrorX = pymmcore.g_Keyword_Transpose_MirrorX
    Transpose_MirrorY = pymmcore.g_Keyword_Transpose_MirrorY
    Transpose_Correction = pymmcore.g_Keyword_Transpose_Correction
    Closed_Position = pymmcore.g_Keyword_Closed_Position
    HubID = pymmcore.g_Keyword_HubID

    # image annotations
    Meatdata_Exposure = pymmcore.g_Keyword_Meatdata_Exposure
    Metadata_Score = pymmcore.g_Keyword_Metadata_Score
    Metadata_ImageNumber = pymmcore.g_Keyword_Metadata_ImageNumber
    Metadata_ROI_X = pymmcore.g_Keyword_Metadata_ROI_X
    Metadata_ROI_Y = pymmcore.g_Keyword_Metadata_ROI_Y
    Metadata_TimeInCore = pymmcore.g_Keyword_Metadata_TimeInCore

    def __str__(self) -> str:
        return str(self.value)


class CFGCommand(str, Enum):
    Device = pymmcore.g_CFGCommand_Device
    Label = pymmcore.g_CFGCommand_Label
    Property = pymmcore.g_CFGCommand_Property
    Configuration = pymmcore.g_CFGCommand_Configuration
    ConfigGroup = pymmcore.g_CFGCommand_ConfigGroup
    Equipment = pymmcore.g_CFGCommand_Equipment
    Delay = pymmcore.g_CFGCommand_Delay
    ImageSynchro = pymmcore.g_CFGCommand_ImageSynchro
    ConfigPixelSize = pymmcore.g_CFGCommand_ConfigPixelSize
    PixelSize_um = pymmcore.g_CFGCommand_PixelSize_um
    PixelSizeAffine = pymmcore.g_CFGCommand_PixelSizeAffine
    ParentID = pymmcore.g_CFGCommand_ParentID
    FocusDirection = pymmcore.g_CFGCommand_FocusDirection
    #
    FieldDelimiters = pymmcore.g_FieldDelimiters

    def __str__(self) -> str:
        return str(self.value)


class CFGGroup(str, Enum):
    System = pymmcore.g_CFGGroup_System
    System_Startup = pymmcore.g_CFGGroup_System_Startup
    System_Shutdown = pymmcore.g_CFGGroup_System_Shutdown
    PixelSizeUm = pymmcore.g_CFGGroup_PixelSizeUm

    def __str__(self) -> str:
        return str(self.value)


class DeviceType(IntEnum):
    UnknownType = pymmcore.UnknownType
    AnyType = pymmcore.AnyType
    CameraDevice = pymmcore.CameraDevice
    ShutterDevice = pymmcore.ShutterDevice
    StateDevice = pymmcore.StateDevice
    StageDevice = pymmcore.StageDevice
    XYStageDevice = pymmcore.XYStageDevice
    SerialDevice = pymmcore.SerialDevice
    GenericDevice = pymmcore.GenericDevice
    AutoFocusDevice = pymmcore.AutoFocusDevice
    CoreDevice = pymmcore.CoreDevice
    ImageProcessorDevice = pymmcore.ImageProcessorDevice
    SignalIODevice = pymmcore.SignalIODevice
    MagnifierDevice = pymmcore.MagnifierDevice
    SLMDevice = pymmcore.SLMDevice
    HubDevice = pymmcore.HubDevice
    GalvoDevice = pymmcore.GalvoDevice
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
    Undef = pymmcore.Undef
    String = pymmcore.String
    Float = pymmcore.Float
    Integer = pymmcore.Integer

    def to_python(self) -> type | None:
        return {0: None, 1: str, 2: float, 3: int}[self]

    def to_json(self) -> str:
        return {0: "null", 1: "string", 2: "number", 3: "integer"}[self]

    def __repr__(self) -> str:
        return getattr(self.to_python(), "__name__", "None")


class ActionType(IntEnum):
    NoAction = pymmcore.NoAction
    BeforeGet = pymmcore.BeforeGet
    AfterSet = pymmcore.AfterSet
    IsSequenceable = pymmcore.IsSequenceable
    AfterLoadSequence = pymmcore.AfterLoadSequence
    StartSequence = pymmcore.StartSequence
    StopSequence = pymmcore.StopSequence


class PortType(IntEnum):
    InvalidPort = pymmcore.InvalidPort
    SerialPort = pymmcore.SerialPort
    USBPort = pymmcore.USBPort
    HIDPort = pymmcore.HIDPort


class FocusDirection(IntEnum):
    FocusDirectionUnknown = pymmcore.FocusDirectionUnknown
    FocusDirectionTowardSample = pymmcore.FocusDirectionTowardSample
    FocusDirectionAwayFromSample = pymmcore.FocusDirectionAwayFromSample
    # aliases
    Unknown = FocusDirectionUnknown
    TowardSample = FocusDirectionTowardSample
    AwayFromSample = FocusDirectionAwayFromSample


class DeviceNotification(IntEnum):
    Attention = pymmcore.Attention
    Done = pymmcore.Done
    StatusChanged = pymmcore.StatusChanged


class DeviceDetectionStatus(IntEnum):
    """DeviceDetectionStatus from device discovery."""

    Unimplemented = pymmcore.Unimplemented
    """There is as yet no mechanism to programmatically detect the device."""
    Misconfigured = pymmcore.Misconfigured
    """Some information needed to communicate with the device is invalid."""
    CanNotCommunicate = pymmcore.CanNotCommunicate
    """Communication attributes are valid, but the device does not respond."""
    CanCommunicate = pymmcore.CanCommunicate
    """Communication verified, parameters have been set to valid values."""


class PixelType(str, Enum):
    UNKNOWN = ""
    GRAY8 = "GRAY8"
    GRAY16 = "GRAY16"
    GRAY32 = "GRAY32"
    RGB32 = "RGB32"
    RGB64 = "RGB64"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def for_bytes(cls, depth: int, n_comp: int = 1) -> PixelType:
        if depth != 4:
            return {1: cls.GRAY8, 2: cls.GRAY16, 8: cls.RGB64, 0: cls.UNKNOWN}[depth]
        return cls.GRAY32 if n_comp == 1 else cls.RGB32
