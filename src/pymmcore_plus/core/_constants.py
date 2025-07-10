from __future__ import annotations

from enum import Enum, IntEnum, auto
from typing import Any, Literal

import pymmcore_plus._pymmcore as pymmcore

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
    Metadata_CameraLabel = pymmcore.g_Keyword_Metadata_CameraLabel
    Metadata_Exposure = pymmcore.g_Keyword_Metadata_Exposure
    Metadata_Height = pymmcore.g_Keyword_Metadata_Height
    Metadata_ImageNumber = pymmcore.g_Keyword_Metadata_ImageNumber
    Metadata_ROI_X = pymmcore.g_Keyword_Metadata_ROI_X
    Metadata_ROI_Y = pymmcore.g_Keyword_Metadata_ROI_Y
    Metadata_Score = pymmcore.g_Keyword_Metadata_Score
    Metadata_TimeInCore = pymmcore.g_Keyword_Metadata_TimeInCore
    Metadata_Width = pymmcore.g_Keyword_Metadata_Width

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

    if hasattr(pymmcore, "g_CFGCommand_PixelSizedxdz"):
        PixelSize_dxdz = pymmcore.g_CFGCommand_PixelSizedxdz
    if hasattr(pymmcore, "g_CFGCommand_PixelSizedydz"):
        PixelSize_dydz = pymmcore.g_CFGCommand_PixelSizedydz
    if hasattr(pymmcore, "g_CFGCommand_PixelSizeOptimalZUm"):
        PixelSize_OptimalZUm = pymmcore.g_CFGCommand_PixelSizeOptimalZUm

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
    PressurePumpDevice = pymmcore.PressurePumpDevice
    VolumetricPumpDevice = pymmcore.VolumetricPumpDevice
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
    PressurePump = PressurePumpDevice
    VolumetricPump = VolumetricPumpDevice

    def __str__(self) -> str:
        return str(self.name).replace("Type", "").replace("Device", "")


class PropertyType(IntEnum):
    Undef = pymmcore.Undef
    String = pymmcore.String
    Float = pymmcore.Float
    Integer = pymmcore.Integer

    Boolean = auto()  # not supported in pymmcore
    Enum = auto()  # not supported in pymmcore

    def to_python(self) -> type | None:
        return {0: None, 1: str, 2: float, 3: int}[self]

    def to_json(self) -> str:
        return {0: "null", 1: "string", 2: "number", 3: "integer"}[self]

    def __repr__(self) -> Literal["undefined", "float", "int", "str"]:
        return getattr(self.to_python(), "__name__", "undefined")

    @classmethod
    def create(cls, value: Any) -> PropertyType:
        if isinstance(value, PropertyType):
            return value
        if value is None:
            return PropertyType.Undef
        if isinstance(value, str):
            if value.lower() in ("int", "integer"):
                return PropertyType.Integer
            if value.lower() in ("float", "double"):
                return PropertyType.Float
            if value.lower() in ("bool", "boolean"):
                return PropertyType.Boolean
            if value.lower() in ("string", "str"):
                return PropertyType.String
            if value.lower() in ("enum", "enumeration"):
                return PropertyType.Enum
        if isinstance(value, type):
            if value is float:
                return PropertyType.Float
            elif value is int:
                return PropertyType.Integer
            elif value is str:
                return PropertyType.String
            elif value is bool:
                return PropertyType.Boolean
            elif issubclass(value, Enum):
                return PropertyType.Enum

        raise TypeError(
            f"Property type must be a PropertyType enum member, "
            f"a string, or a type. Got: {type(value)}"
        )


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


# NB:
# do *not* use `pymmcore.FocusDirection...` enums here.
# the MMCore API does not use the device enums (which is what pymmcore exposes)
# but instead translates MM::FocusDirectionTowardSample into a different number:
# https://github.com/micro-manager/mmCoreAndDevices/tree/MMCore/MMCore.cpp#L2063-L2074
class FocusDirection(IntEnum):
    Unknown = 0
    TowardSample = 1
    AwayFromSample = -1
    # aliases
    FocusDirectionUnknown = Unknown
    FocusDirectionTowardSample = TowardSample
    FocusDirectionAwayFromSample = AwayFromSample


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


class DeviceInitializationState(IntEnum):
    """DeviceInitializationState returned by getDeviceInitializationState."""

    Uninitialized = pymmcore.Uninitialized
    InitializedSuccessfully = pymmcore.InitializedSuccessfully
    InitializationFailed = pymmcore.InitializationFailed


class PixelType(str, Enum):
    """These are pixel types, as used in MMStudio and MMCoreJ wrapper.

    They are only here for supporting the legacy (and probably to-be-deprecated)
    taggedImages.
    """

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
            return {1: cls.GRAY8, 2: cls.GRAY16, 8: cls.RGB64, 0: cls.UNKNOWN}.get(
                depth, cls.UNKNOWN
            )
        return cls.GRAY32 if n_comp == 1 else cls.RGB32

    def to_pixel_format(self) -> PixelFormat:
        return {
            self.GRAY8: PixelFormat.MONO8,
            self.GRAY16: PixelFormat.MONO16,
            self.GRAY32: PixelFormat.MONO32,
            self.RGB32: PixelFormat.RGB8,
            self.RGB64: PixelFormat.RGB16,
        }[self]


class PixelFormat(str, Enum):
    """Subset of GeniCam Pixel Format names used by pymmcore-plus.

    (This is similar to PixelType, but follows GeniCam standards.)

    See <https://docs.baslerweb.com/pixel-format#unpacked-and-packed-pixel-formats>
    for helpful clarifications.  Note that **unpacked** pixel formats (like
    Mono8, Mono12, Mono16) are always 8-bit aligned. Meaning Mono12 is actually
    a 16-bit buffer.

    Attributes
    ----------
    MONO8 : str
        8-bit (unpacked) monochrome pixel format.
    MONO10 : str
        10-bit (unpacked) monochrome pixel format. (16-bit buffer)
    MONO12 : str
        12-bit (unpacked) monochrome pixel format. (16-bit buffer)
    MONO14 : str
        14-bit (unpacked) monochrome pixel format. (16-bit buffer)
    MONO16 : str
        16-bit (unpacked) monochrome pixel format
    MONO32 : str
        32-bit (unpacked) monochrome pixel format
    RGB8 : str
        8-bit RGB pixel format. (24-bit buffer)
    RGB10 : str
        10-bit RGB pixel format. (48-bit buffer)
    RGB12 : str
        12-bit RGB pixel format. (48-bit buffer)
    RGB14 : str
        14-bit RGB pixel format. (48-bit buffer)
    RGB16 : str
        16-bit RGB pixel format. (48-bit buffer)
    """

    MONO8 = "Mono8"
    MONO10 = "Mono10"
    MONO12 = "Mono12"
    MONO14 = "Mono14"
    MONO16 = "Mono16"
    MONO32 = "Mono32"
    RGB8 = "RGB8"
    RGB10 = "RGB10"
    RGB12 = "RGB12"
    RGB14 = "RGB14"
    RGB16 = "RGB16"

    @classmethod
    def pick(cls, bit_depth: int, n_comp: int = 1) -> PixelFormat:
        try:
            return PIXEL_FORMATS[n_comp][bit_depth]
        except KeyError as e:
            raise NotImplementedError(
                f"Unsupported Pixel Format {bit_depth=} {n_comp=}"
            ) from e

    @classmethod
    def for_current_camera(cls, core: pymmcore.CMMCore) -> PixelFormat:
        n_comp = core.getNumberOfComponents()
        if n_comp == 4:
            n_comp = 3
        return cls.pick(core.getImageBitDepth(), n_comp)


# map of {number of components: {bit depth: PixelFormat}}
PIXEL_FORMATS: dict[int, dict[int, PixelFormat]] = {
    1: {
        8: PixelFormat.MONO8,
        10: PixelFormat.MONO10,
        12: PixelFormat.MONO12,
        14: PixelFormat.MONO14,
        16: PixelFormat.MONO16,
        32: PixelFormat.MONO32,
    },
    3: {
        8: PixelFormat.RGB8,
        10: PixelFormat.RGB10,
        12: PixelFormat.RGB12,
        14: PixelFormat.RGB14,
        16: PixelFormat.RGB16,
    },
}
