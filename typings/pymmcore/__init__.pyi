# flake8: noqa
from typing import Any, List, Sequence, Tuple, Type, Union, overload

import numpy as np

AfterLoadSequence: int
AfterSet: int
AnyType: int
Attention: int
AutoFocusDevice: int
BeforeGet: int
CameraDevice: int
CanCommunicate: int
CanNotCommunicate: int
CoreDevice: int
Done: int
Float: int
FocusDirectionAwayFromSample: int
FocusDirectionTowardSample: int
FocusDirectionUnknown: int
GalvoDevice: int
GenericDevice: int
HIDPort: int
HubDevice: int
ImageProcessorDevice: int
Integer: int
InvalidPort: int
IsSequenceable: int
MagnifierDevice: int
MaxStrLength: int
Misconfigured: int
NoAction: int
SLMDevice: int
SerialDevice: int
SerialPort: int
ShutterDevice: int
SignalIODevice: int
StageDevice: int
StartSequence: int
StateDevice: int
StatusChanged: int
StopSequence: int
String: int
USBPort: int
Undef: int
Unimplemented: int
UnknownType: int
XYStageDevice: int

g_CFGCommand_ConfigGroup: str
g_CFGCommand_ConfigPixelSize: str
g_CFGCommand_Configuration: str
g_CFGCommand_Delay: str
g_CFGCommand_Device: str
g_CFGCommand_Equipment: str
g_CFGCommand_FocusDirection: str
g_CFGCommand_ImageSynchro: str
g_CFGCommand_Label: str
g_CFGCommand_ParentID: str
g_CFGCommand_PixelSizeAffine: str
g_CFGCommand_PixelSize_um: str
g_CFGCommand_Property: str
g_CFGGroup_PixelSizeUm: str
g_CFGGroup_System: str
g_CFGGroup_System_Shutdown: str
g_CFGGroup_System_Startup: str
g_FieldDelimiters: str
g_Keyword_ActualExposure: str
g_Keyword_ActualInterval_ms: str
g_Keyword_AnswerTimeout: str
g_Keyword_BaudRate: str
g_Keyword_Binning: str
g_Keyword_CCDTemperature: str
g_Keyword_CCDTemperatureSetPoint: str
g_Keyword_CameraChannelIndex: str
g_Keyword_CameraChannelName: str
g_Keyword_CameraID: str
g_Keyword_CameraName: str
g_Keyword_Channel: str
g_Keyword_Closed_Position: str
g_Keyword_ColorMode: str
g_Keyword_CoreAutoFocus: str
g_Keyword_CoreAutoShutter: str
g_Keyword_CoreCamera: str
g_Keyword_CoreChannelGroup: str
g_Keyword_CoreDevice: str
g_Keyword_CoreFocus: str
g_Keyword_CoreGalvo: str
g_Keyword_CoreImageProcessor: str
g_Keyword_CoreInitialize: str
g_Keyword_CoreSLM: str
g_Keyword_CoreShutter: str
g_Keyword_CoreTimeoutMs: str
g_Keyword_CoreXYStage: str
g_Keyword_DataBits: str
g_Keyword_Delay: str
g_Keyword_DelayBetweenCharsMs: str
g_Keyword_Description: str
g_Keyword_EMGain: str
g_Keyword_Elapsed_Time_ms: str
g_Keyword_Exposure: str
g_Keyword_Gain: str
g_Keyword_Handshaking: str
g_Keyword_HubID: str
g_Keyword_Interval_ms: str
g_Keyword_Label: str
g_Keyword_Meatdata_Exposure: str
g_Keyword_Metadata_ImageNumber: str
g_Keyword_Metadata_ROI_X: str
g_Keyword_Metadata_ROI_Y: str
g_Keyword_Metadata_Score: str
g_Keyword_Metadata_StartTime: str
g_Keyword_Metadata_TimeInCore: str
g_Keyword_Name: str
g_Keyword_Offset: str
g_Keyword_Parity: str
g_Keyword_PixelType: str
g_Keyword_Port: str
g_Keyword_Position: str
g_Keyword_ReadoutMode: str
g_Keyword_ReadoutTime: str
g_Keyword_Speed: str
g_Keyword_State: str
g_Keyword_StopBits: str
g_Keyword_Transpose_Correction: str
g_Keyword_Transpose_MirrorX: str
g_Keyword_Transpose_MirrorY: str
g_Keyword_Transpose_SwapXY: str
g_Keyword_Type: str
g_Keyword_Version: str

DEVICE_BUFFER_OVERFLOW: int
DEVICE_CAMERA_BUSY_ACQUIRING: int
DEVICE_CAN_NOT_SET_PROPERTY: int
DEVICE_COMM_HUB_MISSING: int
DEVICE_CORE_CHANNEL_PRESETS_FAILED: int
DEVICE_CORE_CONFIG_FAILED: int
DEVICE_CORE_EXPOSURE_FAILED: int
DEVICE_CORE_FOCUS_STAGE_UNDEF: int
DEVICE_DUPLICATE_LABEL: int
DEVICE_DUPLICATE_LIBRARY: int
DEVICE_DUPLICATE_PROPERTY: int
DEVICE_ERR: int
DEVICE_IMAGE_PARAMS_FAILED: int
DEVICE_INCOMPATIBLE_IMAGE: int
DEVICE_INTERNAL_INCONSISTENCY: int
DEVICE_INVALID_INPUT_PARAM: int
DEVICE_INVALID_PROPERTY: int
DEVICE_INVALID_PROPERTY_LIMTS: int
DEVICE_INVALID_PROPERTY_TYPE: int
DEVICE_INVALID_PROPERTY_VALUE: int
DEVICE_LOCALLY_DEFINED_ERROR: int
DEVICE_NATIVE_MODULE_FAILED: int
DEVICE_NONEXISTENT_CHANNEL: int
DEVICE_NOT_CONNECTED: int
DEVICE_NOT_SUPPORTED: int
DEVICE_NOT_YET_IMPLEMENTED: int
DEVICE_NO_CALLBACK_REGISTERED: int
DEVICE_NO_PROPERTY_DATA: int
DEVICE_OK: int
DEVICE_OUT_OF_MEMORY: int
DEVICE_PROPERTY_NOT_SEQUENCEABLE: int
DEVICE_SELF_REFERENCE: int
DEVICE_SEQUENCE_TOO_LARGE: int
DEVICE_SERIAL_BUFFER_OVERRUN: int
DEVICE_SERIAL_COMMAND_FAILED: int
DEVICE_SERIAL_INVALID_RESPONSE: int
DEVICE_SERIAL_TIMEOUT: int
DEVICE_SNAP_IMAGE_FAILED: int
DEVICE_UNKNOWN_LABEL: int
DEVICE_UNKNOWN_POSITION: int
DEVICE_UNSUPPORTED_COMMAND: int
DEVICE_UNSUPPORTED_DATA_FORMAT: int
MM_CODE_ERR: int
MM_CODE_OK: int

def CMMCore_addSearchPath(jarg1: str) -> None: ...
def CMMCore_getDeviceLibraries() -> tuple: ...
def CMMCore_noop() -> None: ...
def MetadataTag_ReadLine(jarg: Any) -> str: ...
def PropertySetting_generateKey(device: str, prop: str) -> str: ...

Rectangle = List[int]  # it returns a list of 4 ints... would be nice if it were tuple
DeviceType = int
PropertyType = int
FocusDirection = int
DeviceDetectionStatus = int

class CMMCore:
    def __init__(self) -> None: ...
    def addGalvoPolygonVertex(
        self, galvoLabel: str, polygonIndex: int, x: float, y: float
    ) -> None: ...
    def addSearchPath(self, path: str) -> None: ...
    def assignImageSynchro(self, deviceLabel: str) -> None:
        """Add device to the image-synchro list."""
    def clearCircularBuffer(self) -> None:
        """Removes all images from the circular buffer."""
    def clearROI(self) -> None:
        """Set the region of interest of the current camera to the full frame."""
    def debugLogEnabled(self) -> bool:
        """Indicates if logging of debug messages is enabled"""
    def defineConfig(self, groupName: str, configName: str) -> None:
        """Defines a configuration."""
    def defineConfig(
        self,
        groupName: str,
        configName: str,
        deviceLabel: str,
        propName: str,
        value: str,
    ) -> None: ...
    def defineConfigGroup(self, groupName: str) -> None:
        """Creates an empty configuration group."""
    @overload
    def definePixelSizeConfig(self, resolutionID: str) -> None:
        """Defines an empty pixel size entry."""
    @overload
    def definePixelSizeConfig(
        self, resolutionID: str, deviceLabel: str, propName: str, value: str
    ) -> None: ...
    def definePropertyBlock(
        self, blockName: str, propertyName: str, propertyValue: str
    ) -> None: ...
    def defineStateLabel(
        self, stateDeviceLabel: str, state: int, stateLabel: str
    ) -> None: ...
    @overload
    def deleteConfig(self, groupName: str, configName: str) -> None:
        """Deletes a configuration from a group."""
    @overload
    def deleteConfig(
        self, groupName: str, configName: str, deviceLabel: str, propName: str
    ) -> None: ...
    def deleteConfigGroup(self, groupName: str) -> None:
        """Deletes an entire configuration group."""
    def deleteGalvoPolygons(self, galvoLabel: str) -> None:
        """Remove all added polygons"""
    def deletePixelSizeConfig(self, configName: str) -> None:
        """Deletes a pixel size configuration."""
    def detectDevice(self, deviceLabel: str) -> DeviceDetectionStatus:
        """Tries to communicate to a device through a given serial port Used to automate
        discovery of correct serial port. Also configures the serial port correctly."""
    def deviceBusy(self, label: str) -> bool:
        """Checks the busy status of the specific device."""
    def deviceTypeBusy(self, devType: DeviceType) -> bool:
        """Checks the busy status for all devices of the specific type."""
    def displaySLMImage(self, slmLabel: str) -> None:
        """Display the waiting image on the SLM."""
    def enableContinuousFocus(self, enable: bool) -> None:
        """Enables or disables the operation of the continuous focusing hardware device."""
    def enableDebugLog(self, enable: bool) -> None:
        """Enable or disable logging of debug messages."""
    def enableStderrLog(self, enable: bool) -> None:
        """Enables or disables log message display on the standard console."""
    def fullFocus(self) -> None:
        """Performs focus acquisition and lock for the one-shot focusing device."""
    def getAllowedPropertyValues(self, label: str, propName: str) -> Tuple[str]:
        """Returns all valid values for the specified property."""
    def getAPIVersionInfo(self) -> str:
        """Returns the module and device interface versions."""
    def getAutoFocusDevice(self) -> str:
        """Returns the label of the currently selected auto-focus device."""
    def getAutoFocusOffset(self) -> float:
        """Measures offset for the one-shot focusing device."""
    def getAutoShutter(self) -> bool:
        """Returns the current setting of the auto-shutter option."""
    def getAvailableConfigGroups(self) -> Tuple[str]:
        """Returns the names of all defined configuration groups"""
    def getAvailableConfigs(self, configGroup: str) -> Tuple[str]:
        """Returns all defined configuration names in a given group"""
    def getAvailableDeviceDescriptions(self, library: str) -> Tuple[str]:
        """Get descriptions for available devices from the specified library."""
    def getAvailableDevices(self, library: str) -> Tuple[str]:
        """Get available devices from the specified device library."""
    def getAvailableDeviceTypes(self, library: str) -> Tuple[int]:
        """Get type information for available devices from the specified library."""
    def getAvailablePixelSizeConfigs(self) -> Tuple[str]:
        """Returns all defined resolution preset names"""
    def getAvailablePropertyBlocks(self) -> Tuple[str]:
        """Returns all defined property block identifiers."""
    def getBufferFreeCapacity(self) -> int:
        """Returns the number of images that can be added to the buffer without
        overflowing.
        """
    def getBufferTotalCapacity(self) -> int:
        """Returns the total number of images that can be stored in the buffer"""
    def getBytesPerPixel(self) -> int:
        """How many bytes for each pixel."""
    def getCameraChannelName(self, channelNr: int) -> str:
        """Returns the name of the requested channel as known by the default camera"""
    def getCameraDevice(self) -> str:
        """Returns the label of the currently selected camera device."""
    def getChannelGroup(self) -> str:
        """Returns the group determining the channel selection."""
    def getCircularBufferMemoryFootprint(self) -> int:
        """Returns the size of the Circular Buffer in MB"""
    def getConfigData(self, configGroup: str, configName: str) -> Configuration:
        """Returns the configuration object for a given group and name."""
    def getConfigGroupState(self, group: str) -> Configuration:
        """Returns the partial state of the system, only for the devices included in the
        specified group."""
    def getConfigGroupStateFromCache(self, group: str) -> Configuration:
        """Returns the partial state of the system cache, only for the devices included in
        the specified group."""
    def getConfigState(self, group: str, config: str) -> Configuration:
        """Returns a partial state of the system, only for devices included in the
        specified configuration."""
    def getCoreErrorText(self, code: int) -> str:
        """Returns a pre-defined error test with the given error code"""
    def getCurrentConfig(self, groupName: str) -> str:
        """Returns the current configuration for a given group."""
    def getCurrentConfigFromCache(self, groupName: str) -> str:
        """Returns the configuration for a given group based on the data in the cache."""
    def getCurrentFocusScore(self) -> float:
        """Returns the focus score from the default focusing device measured at the
        current Z position."""
    @overload
    def getCurrentPixelSizeConfig(self) -> str:
        """Get the current pixel configuration name"""
    @overload
    def getCurrentPixelSizeConfig(self, cached: bool) -> str:
        """Get the current pixel configuration name"""
    def getData(self, stateDeviceLabel: str) -> PropertyBlock:
        """Returns the collection of property-value pairs defined for the current state."""
    def getDeviceAdapterNames(self) -> Tuple[str]:
        """Return the names of discoverable device adapters."""
    def getDeviceAdapterSearchPaths(self) -> Tuple[str]:
        """Return the current device adapter search paths."""
    def getDeviceDelayMs(self, label: str) -> float:
        """Reports action delay in milliseconds for the specific device."""
    def getDeviceDescription(self, label: str) -> str:
        """Returns description text for a given device label. "Description" is determined
        by the library and is immutable."""
    def getDeviceLibraries(self) -> Tuple[str]: ...
    def getDeviceLibrary(self, label: str) -> str:
        """Returns device library (aka module, device adapter) name."""
    def getDeviceName(self, label: str) -> str:
        """Returns device name for a given device label."""
    def getDevicePropertyNames(self, label: str) -> Tuple[str]:
        """Returns all property names supported by the device."""
    def getDeviceType(self, label: str) -> DeviceType:
        """Returns device type."""
    @overload
    def getExposure(self) -> float:
        """Returns the current exposure setting of the camera in milliseconds."""
    @overload
    def getExposure(self, label: str) -> float:
        """Returns the current exposure setting of the specified camera in milliseconds."""
    def getExposureSequenceMaxLength(self, cameraLabel: str) -> int:
        """Gets the maximum length of a camera's exposure sequence."""
    def getFocusDevice(self) -> str:
        """Returns the label of the currently selected focus device."""
    def getFocusDirection(self, stageLabel: str) -> FocusDirection:
        """Get the focus direction of a stage."""
    def getGalvoChannel(self, galvoLabel: str) -> str:
        """Get the name of the active galvo channel (for a multi-laser galvo device)."""
    def getGalvoDevice(self) -> str:
        """Returns the label of the currently selected Galvo device."""
    @overload
    def getGalvoPosition(self, galvoDevice: str) -> List[float]: ...
    @overload
    def getGalvoPosition(
        self, galvoLabel: str, x_stage: Sequence[float], y_stage: Sequence[float]
    ) -> None: ...
    def getGalvoXMinimum(self, galvoLabel: str) -> float:
        """Get the Galvo x minimum"""
    def getGalvoXRange(self, galvoLabel: str) -> float:
        """Get the Galvo x range"""
    def getGalvoYMinimum(self, galvoLabel: str) -> float:
        """Get the Galvo y minimum"""
    def getGalvoYRange(self, galvoLabel: str) -> float:
        """Get the Galvo y range"""
    def getHostName(self) -> str:
        """return current computer name."""
    @overload
    def getImage(self) -> np.ndarray:
        """Exposes the internal image buffer."""
    @overload
    def getImage(self, numChannel: int) -> np.ndarray:
        """Returns the internal image buffer for a given Camera Channel"""
    def getImageBitDepth(self) -> int:
        """How many bits of dynamic range are to be expected from the camera."""
    def getImageBufferSize(self) -> int:
        """Returns the size of the internal image buffer."""
    def getImageHeight(self) -> int:
        """Vertical dimension of the image buffer in pixels."""
    def getImageProcessorDevice(self) -> str:
        """Returns the label of the currently selected image processor device."""
    def getImageWidth(self) -> int:
        """Horizontal dimension of the image buffer in pixels."""
    def getInstalledDeviceDescription(
        self, hubLabel: str, peripheralLabel: str
    ) -> str: ...
    def getInstalledDevices(self, hubLabel: str) -> Tuple[str]:
        """Performs auto-detection and loading of child devices that are attached to a
        Hub device."""
    def getLastFocusScore(self) -> float:
        """Returns the latest focus score from the focusing device."""
    def getLastImage(self) -> Any:
        """Gets the last image from the circular buffer."""
    @overload
    def getLastImageMD(self, channel: int, slice: int, md: Metadata) -> np.ndarray: ...
    @overload
    def getLastImageMD(self, md: Metadata) -> np.ndarray:
        """Returns a pointer to the pixels of the image that was last inserted into the
        circular buffer. Also provides all metadata associated with that image"""
    def getLoadedDevices(self) -> Tuple[str]:
        """Returns an array of labels for currently loaded devices."""
    def getLoadedDevicesOfType(self, devType: DeviceType) -> Tuple[str]:
        """Returns an array of labels for currently loaded devices of specific type."""
    def getLoadedPeripheralDevices(self, hubLabel: str) -> Tuple[str]: ...
    def getMACAddresses(self) -> Tuple[str]: ...
    def getMagnificationFactor(self) -> float:
        """Returns the product of all Magnifiers in the system or 1.0 when none is found.
        This is used internally by GetPixelSizeUm"""
    # def getMultiROI(self) -> List[Any]: ...  # this overload doesn't seem to be present
    def getMultiROI(
        self,
        xs: Sequence[int],
        ys: Sequence[int],
        widths: Sequence[int],
        heights: Sequence[int],
    ) -> None: ...
    def getNBeforeLastImageMD(self, n: int, md: Metadata) -> Any:
        """Returns a pointer to the pixels of the image that was inserted n images ago.
        Also provides all metadata associated with that image"""
    def getNumberOfCameraChannels(self) -> int:
        """Returns the number of simultaneous channels the default camera is returning."""
    def getNumberOfComponents(self) -> int:
        """Returns the number of components the default camera is returning."""
    def getNumberOfStates(self, stateDeviceLabel: str) -> int:
        """Returns the total number of available positions (states)."""
    def getParentLabel(self, peripheralLabel: str) -> str:
        """Returns parent device."""
    @overload
    def getPixelSizeAffine(self) -> Tuple[float]:
        """Returns the current Affine Transform to related camera pixels with
        stage movement."""
    @overload
    def getPixelSizeAffine(self, cached: bool) -> Tuple[float]:
        """Returns the current Affine Transform to related camera pixels with
        stage movement."""
    def getPixelSizeAffineAsString(self) -> str:
        """Convenience function."""
    def getPixelSizeAffineByID(self, resolutionID: str) -> Tuple[float]:
        """Returns the Affine Transform to related camera pixels with stage movement for
        the requested pixel size group. The raw affine transform without correction for
        binning and magnification will be returned."""
    def getPixelSizeConfigData(self, configName: str) -> Configuration:
        """Returns the configuration object for a give pixel size preset."""
    @overload
    def getPixelSizeUm(self) -> float:
        """Returns the current pixel size in microns."""
    @overload
    def getPixelSizeUm(self, cached: bool) -> float:
        """Returns the current pixel size in microns."""
    def getPixelSizeUmByID(self, resolutionID: str) -> float:
        """Returns the pixel size in um for the requested pixel size group"""
    @overload
    def getPosition(self) -> float:
        """Returns the current position of the stage in microns."""
    @overload
    def getPosition(self, stageLabel: str) -> float:
        """Returns the current position of the stage in microns."""
    def getPrimaryLogFile(self) -> str:
        """Return the name of the primary Core log file."""
    def getProperty(self, label: str, propName: str) -> str:
        """Returns the property value for the specified device."""
    def getPropertyBlockData(self, blockName: str) -> PropertyBlock:
        """Returns the collection of property-value pairs defined in this block."""
    def getPropertyFromCache(self, deviceLabel: str, propName: str) -> str:
        """Returns the cached property value for the specified device."""
    def getPropertyLowerLimit(self, label: str, propName: str) -> float:
        """Returns the property lower limit value, if the property has limits - 0
        otherwise."""
    def getPropertySequenceMaxLength(self, label: str, propName: str) -> int:
        """Queries device property for the maximum number of events that can be put
        in a sequence"""
    def getPropertyType(self, label: str, propName: str) -> PropertyType:
        """Returns the intrinsic property type."""
    def getPropertyUpperLimit(self, label: str, propName: str) -> float:
        """Returns the property upper limit value, if the property has limits - 0
        otherwise."""
    def getRemainingImageCount(self) -> int:
        """Returns number ofimages available in the Circular Buffer"""
    @overload
    def getROI(self) -> Rectangle: ...
    @overload
    def getROI(self, label: str) -> Rectangle: ...
    # these overloads don't seem to work?
    # def getROI(self, x: int, y: int, xSize: int, ySize: int) -> None: ...
    # def getROI(self, label: str, x: int, y: int, xSize: int, ySize: int) -> None: ...
    def getSerialPortAnswer(self, portLabel: str, term: str) -> str:
        """Continuously read from the serial port until the terminating sequence is
        encountered."""
    def getShutterDevice(self) -> str:
        """Returns the label of the currently selected shutter device."""
    @overload
    def getShutterOpen(self) -> bool:
        """Returns the state of the currently selected (default) shutter."""
    @overload
    def getShutterOpen(self, shutterLabel: str) -> bool:
        """Returns the state of the specified shutter."""
    def getSLMBytesPerPixel(self, slmLabel: str) -> int:
        """Returns the number of bytes per SLM pixel"""
    def getSLMDevice(self) -> str:
        """Returns the label of the currently selected SLM device."""
    def getSLMExposure(self, slmLabel: str) -> float:
        """Returns the exposure time that will be used by the SLM for illumination"""
    def getSLMHeight(self, slmLabel: str) -> int:
        """Returns the height (in "pixels") of the SLM"""
    def getSLMNumberOfComponents(self, slmLabel: str) -> int:
        """Returns the number of components (usually these depict colors) of the SLM.

        For instance, an RGB projector will return 3, but a grey scale SLM returns 1"""
    def getSLMSequenceMaxLength(self, slmLabel: str) -> int:
        """For SLMs that support sequences, returns the maximum length of the sequence
        that can be uploaded to the device"""
    def getSLMWidth(self, slmLabel: str) -> int:
        """Returns the width (in "pixels") of the SLM"""
    def getStageSequenceMaxLength(self, stageLabel: str) -> int:
        """Gets the maximum length of a stage's position sequence."""
    def getState(self, stateDeviceLabel: str) -> int:
        """Returns the current state (position) on the specific device."""
    def getStateFromLabel(self, stateDeviceLabel: str, stateLabel: str) -> int:
        """Obtain the state for a given label."""
    def getStateLabel(self, stateDeviceLabel: str) -> str:
        """Returns the current state as the label (string)."""
    def getStateLabelData(
        self, stateDeviceLabel: str, stateLabel: str
    ) -> PropertyBlock:
        """Returns the collection of property-value pairs defined for the specific
        device and state label."""
    def getStateLabels(self, stateDeviceLabel: str) -> Tuple[str]:
        """Return labels for all states"""
    def getSystemState(self) -> Configuration:
        """Returns the entire system state, i.e."""
    def getSystemStateCache(self) -> Configuration:
        """Returns the entire system state, i.e."""
    def getTimeoutMs(self) -> int: ...
    def getUserId(self) -> str:
        """Displays current user name."""
    def getVersionInfo(self) -> str:
        """Displays core version."""
    @overload
    def getXPosition(self) -> float:
        """Obtains the current position of the X axis of the XY stage in microns."""
    @overload
    def getXPosition(self, xyStageLabel: str) -> float:
        """Obtains the current position of the X axis of the XY stage in microns."""
    @overload
    def getXYPosition(self, x_stage: Sequence[float], y_stage: Sequence[float]) -> None:
        """Obtains the current position of the XY stage in microns."""
    @overload
    def getXYPosition(
        self, xyStageLabel: str, x_stage: Sequence[float], y_stage: Sequence[float]
    ) -> None: ...
    def getXYStageDevice(self) -> str:
        """Returns the label of the currently selected XYStage device."""
    @overload
    def getXYStagePosition(self) -> List[float]:
        """Convenience function: returns the current XY position of the current
        XY stage device as a Point2D.Double."""
    @overload
    def getXYStagePosition(self, stage: str) -> List[float]: ...
    def getXYStageSequenceMaxLength(self, xyStageLabel: str) -> int:
        """Gets the maximum length of an XY stage's position sequence."""
    @overload
    def getYPosition(self) -> float:
        """Obtains the current position of the Y axis of the XY stage in microns."""
    @overload
    def getYPosition(self, xyStageLabel: str) -> float:
        """Obtains the current position of the Y axis of the XY stage in microns."""
    def hasProperty(self, label: str, propName: str) -> bool:
        """Checks if device has a property with a specified name."""
    def hasPropertyLimits(self, label: str, propName: str) -> bool:
        """Queries device if the specific property has limits."""
    def home(self, xyOrZStageLabel: str) -> None:
        """Perform a hardware homing operation for an XY or focus/Z stage."""
    def incrementalFocus(self) -> None:
        """Performs incremental focus for the one-shot focusing device."""
    def initializeAllDevices(self) -> None:
        """Calls Initialize() method for each loaded device."""
    def initializeCircularBuffer(self) -> None:
        """Initialize circular buffer based on the current camera settings."""
    def initializeDevice(self, label: str) -> None:
        """Initializes specific device."""
    def isBufferOverflowed(self) -> bool:
        """Indicates whether the circular buffer is overflowed"""
    def isConfigDefined(self, groupName: str, configName: str) -> bool:
        """Checks if the configuration already exists within a group."""
    def isContinuousFocusDrive(self, stageLabel: str) -> bool:
        """Check if a stage has continuous focusing capability.

        (positions can be set while continuous focus runs)."""
    def isContinuousFocusEnabled(self) -> bool:
        """Checks if the continuous focusing hardware device is ON or OFF."""
    def isContinuousFocusLocked(self) -> bool:
        """Returns the lock-in status of the continuous focusing device."""
    def isExposureSequenceable(self, cameraLabel: str) -> bool:
        """Queries camera if exposure can be used in a sequence"""
    def isGroupDefined(self, groupName: str) -> bool:
        """Checks if the group already exists."""
    def isMultiROIEnabled(self) -> bool:
        """Queries the camera to determine if multiple ROIs are currently set."""
    def isMultiROISupported(self) -> bool:
        """Queries the camera to determine if it supports multiple ROIs."""
    def isPixelSizeConfigDefined(self, resolutionID: str) -> bool:
        """Checks if the Pixel Size Resolution already exists"""
    def isPropertyPreInit(self, label: str, propName: str) -> bool:
        """Tells us whether the property must be defined prior to initialization."""
    def isPropertyReadOnly(self, label: str, propName: str) -> bool:
        """Tells us whether the property can be modified."""
    def isPropertySequenceable(self, label: str, propName: str) -> bool:
        """Queries device if the specified property can be used in a sequence"""
    @overload
    def isSequenceRunning(self) -> bool:
        """Check if the current camera is acquiring the sequence.

        Returns false when the sequence is done"""
    @overload
    def isSequenceRunning(self, cameraLabel: str) -> bool:
        """Check if the specified camera is acquiring the sequence.

        Returns false when the sequence is done"""
    def isStageLinearSequenceable(self, stageLabel: str) -> bool:
        """Queries if the stage can be used in a linear sequence.

        A linear sequence is defined by a stepsize and number of slices"""
    def isStageSequenceable(self, stageLabel: str) -> bool:
        """Queries stage if it can be used in a sequence"""
    def isXYStageSequenceable(self, xyStageLabel: str) -> bool:
        """Queries XY stage if it can be used in a sequence"""
    def loadDevice(self, label: str, moduleName: str, deviceName: str) -> None: ...
    def loadExposureSequence(
        self, cameraLabel: str, exposureSequence_ms: Sequence[float]
    ) -> None:
        """Transfer a sequence of exposure times to the camera."""
    def loadGalvoPolygons(self, galvoLabel: str) -> None:
        """Load a set of galvo polygons to the device"""
    def loadPropertySequence(
        self, label: str, propName: str, eventSequence: Sequence[str]
    ) -> None: ...
    def loadSLMSequence(self, slmLabel: str, imageSequence: List[bytes]) -> None:
        """Load a sequence of images into the SLM"""
    def loadStageSequence(
        self, stageLabel: str, positionSequence: Sequence[float]
    ) -> None:
        """Transfer a sequence of events/states/whatever to the device.

        This should only be called for device-properties that are sequenceable"""
    def loadSystemConfiguration(self, fileName: str) -> None:
        """Loads the system configuration from the text file conforming to the
        MM specific format."""
    def loadSystemState(self, fileName: str) -> None:
        """Loads the system configuration from the text file conforming to the
        MM specific format."""
    def loadXYStageSequence(
        self, xyStageLabel: str, xSequence: Sequence[float], ySequence: Sequence[float]
    ) -> None: ...
    @overload
    def logMessage(self, msg: str) -> None:
        """Record text message in the log file."""
    @overload
    def logMessage(self, msg: str, debugOnly: bool) -> None:
        """Record text message in the log file."""
    def noop(self) -> None:
        """A static method that does nothing."""
    def pointGalvoAndFire(
        self, galvoLabel: str, x: float, y: float, pulseTime_us: float
    ) -> None: ...
    def popNextImage(self) -> Any:
        """Gets and removes the next image from the circular buffer."""
    @overload
    def popNextImageMD(self, channel: int, slice: int, md: Metadata) -> Any: ...
    @overload
    def popNextImageMD(self, md: Metadata) -> Any:
        """Gets and removes the next image (and metadata) from the circular buffer"""
    def prepareSequenceAcquisition(self, cameraLabel: str) -> None:
        """Prepare the camera for the sequence acquisition to save the time in the

        StartSequenceAcqusition() call which is supposed to come next."""
    def readFromSerialPort(self, portLabel: str) -> List[str]:  # charvector
        """Reads the contents of the Rx buffer."""
    def registerCallback(self, cb: MMEventCallback) -> None:
        """Register a callback (listener class)."""
    def removeImageSynchro(self, deviceLabel: str) -> None:
        """Removes device from the image-synchro list."""
    def removeImageSynchroAll(self) -> None:
        """Clears the image synchro device list."""
    def renameConfig(
        self, groupName: str, oldConfigName: str, newConfigName: str
    ) -> None: ...
    def renameConfigGroup(self, oldGroupName: str, newGroupName: str) -> None:
        """Renames a configuration group."""
    def renamePixelSizeConfig(self, oldConfigName: str, newConfigName: str) -> None:
        """Renames a pixel size configuration."""
    def reset(self) -> None:
        """Unloads all devices from the core, clears all configuration data and property
        blocks."""
    def runGalvoPolygons(self, galvoLabel: str) -> None:
        """Run a loop of galvo polygons"""
    def runGalvoSequence(self, galvoLabel: str) -> None:
        """Run a sequence of galvo positions"""
    def saveSystemConfiguration(self, fileName: str) -> None:
        """Saves the current system configuration to a text file of the MM specific format."""
    def saveSystemState(self, fileName: str) -> None:
        """Saves the current system state to a text file of the MM specific format."""
    @overload
    def setAdapterOrigin(self, newZUm: float) -> None:
        """Enable software translation of coordinates for the current focus/Z stage."""
    @overload
    def setAdapterOrigin(self, stageLabel: str, newZUm: float) -> None:
        """Enable software translation of coordinates for the given focus/Z stage."""
    @overload
    def setAdapterOriginXY(self, newXUm: float, newYUm: float) -> None:
        """Enable software translation of coordinates for the current XY stage."""
    @overload
    def setAdapterOriginXY(
        self, xyStageLabel: str, newXUm: float, newYUm: float
    ) -> None: ...
    def setAutoFocusDevice(self, focusLabel: str) -> None:
        """Sets the current auto-focus device."""
    def setAutoFocusOffset(self, offset: float) -> None:
        """Applies offset the one-shot focusing device."""
    def setAutoShutter(self, state: bool) -> None:
        """If this option is enabled Shutter automatically opens and closes when the
        image is acquired."""
    def setCameraDevice(self, cameraLabel: str) -> None:
        """Sets the current camera device."""
    def setChannelGroup(self, channelGroup: str) -> None:
        """Specifies the group determining the channel selection."""
    def setCircularBufferMemoryFootprint(self, sizeMB: int) -> None:
        """Reserve memory for the circular buffer."""
    def setConfig(self, groupName: str, configName: str) -> None:
        """Applies a configuration to a group."""
    def setDeviceAdapterSearchPaths(self, paths: Sequence[str]) -> None:
        """Set the device adapter search paths."""
    def setDeviceDelayMs(self, label: str, delayMs: float) -> None:
        """Overrides the built-in value for the action delay."""
    @overload
    def setExposure(self, exp: float) -> None:
        """Sets the exposure setting of the current camera in milliseconds."""
    @overload
    def setExposure(self, cameraLabel: str, dExp: float) -> None:
        """Sets the exposure setting of the specified camera in milliseconds."""
    def setFocusDevice(self, focusLabel: str) -> None:
        """Sets the current focus device."""
    def setFocusDirection(self, stageLabel: str, sign: int) -> None:
        """Set the focus direction of a stage."""
    def setGalvoDevice(self, galvoLabel: str) -> None:
        """Sets the current galvo device."""
    def setGalvoIlluminationState(self, galvoLabel: str, on: bool) -> None:
        """Set the galvo's illumination state to on or off"""
    def setGalvoPolygonRepetitions(self, galvoLabel: str, repetitions: int) -> None:
        """Set the number of times to loop galvo polygons"""
    def setGalvoPosition(self, galvoLabel: str, x: float, y: float) -> None: ...
    def setGalvoSpotInterval(self, galvoLabel: str, pulseTime_us: float) -> None: ...
    def setImageProcessorDevice(self, procLabel: str) -> None:
        """Sets the current image processor device."""
    @overload
    def setMultiROI(self, rects: List[Any]) -> None: ...
    @overload
    def setMultiROI(
        self,
        xs: Sequence[int],
        ys: Sequence[int],
        widths: Sequence[int],
        heights: Sequence[int],
    ) -> None: ...
    @overload
    def setOrigin(self) -> None:
        """Zero the current focus/Z stage's coordinates at the current position."""
    @overload
    def setOrigin(self, stageLabel: str) -> None:
        """Zero the given focus/Z stage's coordinates at the current position."""
    @overload
    def setOriginX(self) -> None:
        """Zero the given XY stage's X coordinate at the current position."""
    @overload
    def setOriginX(self, xyStageLabel: str) -> None:
        """Zero the given XY stage's X coordinate at the current position."""
    @overload
    def setOriginXY(self) -> None:
        """Zero the current XY stage's coordinates at the current position."""
    @overload
    def setOriginXY(self, xyStageLabel: str) -> None:
        """Zero the given XY stage's coordinates at the current position."""
    @overload
    def setOriginY(self) -> None:
        """Zero the given XY stage's Y coordinate at the current position."""
    @overload
    def setOriginY(self, xyStageLabel: str) -> None:
        """Zero the given XY stage's Y coordinate at the current position."""
    def setParentLabel(self, deviceLabel: str, parentHubLabel: str) -> None:
        """Sets parent device label"""
    def setPixelSizeAffine(self, resolutionID: str, affine: Sequence[float]) -> None:
        """Sets the raw affine transform for the specific pixel size configuration.

        The affine transform consists of the first two rows of a 3x3 matrix,
        the third row is alsways assumed to be 0.0 0.0 1.0."""
    def setPixelSizeConfig(self, resolutionID: str) -> None:
        """Applies a Pixel Size Configuration."""
    def setPixelSizeUm(self, resolutionID: str, pixSize: float) -> None:
        """Sets pixel size in microns for the specified resolution sensing
        configuration preset."""
    @overload
    def setPosition(self, position: float) -> None:
        """Sets the position of the stage in microns."""
    @overload
    def setPosition(self, stageLabel: str, position: float) -> None:
        """Sets the position of the stage in microns."""
    @overload
    def setPrimaryLogFile(self, filename: str) -> None: ...
    @overload
    def setPrimaryLogFile(self, filename: str, truncate: bool) -> None:
        """Set the primary Core log file."""
    def setProperty(
        self, label: str, propName: str, propValue: Union[bool, float, int, str]
    ) -> None: ...
    @overload
    def setRelativePosition(self, d: float) -> None:
        """Sets the relative position of the stage in microns."""
    @overload
    def setRelativePosition(self, stageLabel: str, d: float) -> None:
        """Sets the relative position of the stage in microns."""
    @overload
    def setRelativeXYPosition(self, dx: float, dy: float) -> None:
        """Sets the relative position of the XY stage in microns."""
    @overload
    def setRelativeXYPosition(
        self, xyStageLabel: str, dx: float, dy: float
    ) -> None: ...
    @overload
    def setROI(self, x: int, y: int, xSize: int, ySize: int) -> None: ...
    @overload
    def setROI(self, label: str, x: int, y: int, xSize: int, ySize: int) -> None: ...
    def setSerialPortCommand(self, portLabel: str, command: str, term: str) -> None: ...
    def setSerialProperties(
        self,
        portName: str,
        answerTimeout: str,
        baudRate: str,
        delayBetweenCharsMs: str,
        handshaking: str,
        parity: str,
        stopBits: str,
    ) -> None: ...
    def setShutterDevice(self, shutterLabel: str) -> None:
        """the current shutter device."""
    @overload
    def setShutterOpen(self, state: bool) -> None:
        """Opens or closes the currently selected (default) shutter."""
    @overload
    def setShutterOpen(self, shutterLabel: str, state: bool) -> None:
        """Opens or closes the specified shutter."""
    def setSLMDevice(self, slmLabel: str) -> None:
        """Sets the current slm device."""
    def setSLMExposure(self, slmLabel: str, exposure_ms: float) -> None:
        """For SLM devices with build-in light source (such as projectors),

        this will set the exposure time, but not (yet) start the illumination"""
    @overload
    def setSLMImage(self, slmLabel: str, pixels: Any) -> None:
        """Write a 32-bit color image to the SLM."""
    @overload
    def setSLMImage(self, slmLabel: str, pixels: Sequence[int]) -> None:
        """Write a 32-bit color image to the SLM."""
    @overload
    def setSLMPixelsTo(self, slmLabel: str, intensity: int) -> None:
        """Set all SLM pixels to a single 8-bit intensity."""
    @overload
    def setSLMPixelsTo(
        self, slmLabel: str, red: int, green: int, blue: int
    ) -> None: ...
    def setStageLinearSequence(
        self, stageLabel: str, dZ_um: float, nSlices: int
    ) -> None: ...
    def setState(self, stateDeviceLabel: str, state: int) -> None:
        """Sets the state (position) on the specific device."""
    def setStateLabel(self, stateDeviceLabel: str, stateLabel: str) -> None:
        """Sets device state using the previously assigned label (string)."""
    def setSystemState(self, conf: Configuration) -> None:
        """Sets all properties contained in the Configuration object."""
    def setTimeoutMs(self, timeoutMs: int) -> None: ...
    @overload
    def setXYPosition(self, x: float, y: float) -> None:
        """Sets the position of the XY stage in microns."""
    @overload
    def setXYPosition(self, xyStageLabel: str, x: float, y: float) -> None: ...
    def setXYStageDevice(self, xyStageLabel: str) -> None:
        """Sets the current XY device."""
    def sleep(self, intervalMs: float) -> None:
        """Waits (blocks the calling thread) for specified time in milliseconds."""
    def snapImage(self) -> None:
        """Acquires a single image with current settings."""
    def startContinuousSequenceAcquisition(self, intervalMs: float) -> None:
        """Starts the continuous camera sequence acquisition."""
    def startExposureSequence(self, cameraLabel: str) -> None:
        """Starts an ongoing sequence of triggered exposures in a camera.

        This should only be called for cameras where exposure time is sequenceable"""
    def startPropertySequence(self, label: str, propName: str) -> None:
        """Starts an ongoing sequence of triggered events in a property of a device.

        This should only be called for device-properties that are sequenceable"""
    @overload
    def startSecondaryLogFile(self, filename: str, enableDebug: bool) -> int: ...
    @overload
    def startSecondaryLogFile(
        self, filename: str, enableDebug: bool, truncate: bool
    ) -> int: ...
    @overload
    def startSecondaryLogFile(
        self, filename: str, enableDebug: bool, truncate: bool, synchronous: bool
    ) -> int: ...
    @overload
    def startSequenceAcquisition(
        self, numImages: int, intervalMs: float, stopOnOverflow: bool
    ) -> None: ...
    @overload
    def startSequenceAcquisition(
        self, cameraLabel: str, numImages: int, intervalMs: float, stopOnOverflow: bool
    ) -> None: ...
    def startSLMSequence(self, slmLabel: str) -> None:
        """Starts the sequence previously uploaded to the SLM"""
    def startStageSequence(self, stageLabel: str) -> None:
        """Starts an ongoing sequence of triggered events in a stage.

        This should only be called for stages"""
    def startXYStageSequence(self, xyStageLabel: str) -> None:
        """Starts an ongoing sequence of triggered events in an XY stage.

        This should only be called for stages"""
    def stderrLogEnabled(self) -> bool:
        """Indicates whether logging output goes to stdErr"""
    def stop(self, xyOrZStageLabel: str) -> None:
        """Stop the XY or focus/Z stage motors"""
    def stopExposureSequence(self, cameraLabel: str) -> None:
        """Stops an ongoing sequence of triggered exposures in a camera.

        This should only be called for cameras where exposure time is sequenceable"""
    def stopPropertySequence(self, label: str, propName: str) -> None:
        """Stops an ongoing sequence of triggered events in a property of a device.

        This should only be called for device-properties that are sequenceable"""
    def stopSecondaryLogFile(self, handle: int) -> None:
        """Stop capturing logging output into an additional file."""
    @overload
    def stopSequenceAcquisition(self) -> None:
        """Stops streaming camera sequence acquisition."""
    @overload
    def stopSequenceAcquisition(self, cameraLabel: str) -> None:
        """Stops streaming camera sequence acquisition for a specified camera."""
    def stopSLMSequence(self, slmLabel: str) -> None:
        """Stops the SLM sequence if previously started"""
    def stopStageSequence(self, stageLabel: str) -> None:
        """Stops an ongoing sequence of triggered events in a stage.

        This should only be called for stages that are sequenceable"""
    def stopXYStageSequence(self, xyStageLabel: str) -> None:
        """Stops an ongoing sequence of triggered events in an XY stage.

        This should only be called for stages that are sequenceable"""
    def supportsDeviceDetection(self, deviceLabel: str) -> bool:
        """Return whether or not the device supports automatic device detection (i.e."""
    def systemBusy(self) -> bool:
        """Checks the busy status of the entire system."""
    def unloadAllDevices(self) -> None:
        """Unloads all devices from the core and resets all configuration data."""
    def unloadDevice(self, label: str) -> None:
        """Unloads the device from the core and adjusts all configuration data."""
    def unloadLibrary(self, moduleName: str) -> None:
        """Forcefully unload a library."""
    def updateCoreProperties(self) -> None:
        """Updates CoreProperties (currently all Core properties are devices types) with
        the loaded hardware."""
    def updateSystemStateCache(self) -> None:
        """Updates the state of the entire hardware."""
    def usesDeviceDelay(self, label: str) -> bool:
        """Signals if the device will use the delay setting or not."""
    def waitForConfig(self, group: str, configName: str) -> None:
        """Blocks until all devices included in the configuration become ready."""
    def waitForDevice(self, label: str) -> None:
        """Waits (blocks the calling thread) until the specified device becomes non-busy."""
    def waitForDeviceType(self, devType: DeviceType) -> None:
        """Blocks until all devices of the specific type become ready (not-busy)."""
    def waitForImageSynchro(self) -> None:
        """Wait for the slowest device in the ImageSynchro list."""
    def waitForSystem(self) -> None:
        """Blocks until all devices in the system become ready (not-busy)."""
    def writeToSerialPort(self, portLabel: str, data: bytes) -> None:
        """Sends an array of characters to the serial port and returns immediately."""
    # def getTaggedImage(self) -> TaggedImage: ...
    # def getTaggedImage(self, cameraChannelIndex: int) -> TaggedImage: ...
    # def getNBeforeLastTaggedImage(self, n: int) -> TaggedImage: ...
    # def getLastTaggedImage(self) -> TaggedImage: ...
    # def getLastTaggedImage(self,cameraChannelIndex: int) -> TaggedImage: ...
    # def popNextTaggedImage(self) -> TaggedImage: ...
    # def popNextTaggedImage(self, cameraChannelIndex: int) -> TaggedImage: ...

ErrorCode = int

class CMMError:
    @overload
    def __init__(self, msg: str, code: ErrorCode = 1): ...
    @overload
    def __init__(self, msg: str, code: ErrorCode, underlyingError: CMMError): ...
    @overload
    def __init__(self, msg: str, underlyingError: CMMError): ...
    @overload
    def __init__(self, other: CMMError): ...
    def getCode(self) -> ErrorCode: ...
    def getFullMsg(self) -> str: ...
    def getMsg(self) -> str: ...
    def getSpecificCode(self) -> ErrorCode: ...
    def getUnderlyingError(self) -> CMMError: ...
    def what(self) -> str: ...

class Configuration:
    def __init__(self) -> None: ...
    def addSetting(self, setting: PropertySetting) -> None: ...
    def deleteSetting(self, device: str, prop, str) -> None: ...
    @overload
    def getSetting(self, index: int) -> PropertySetting: ...
    @overload
    def getSetting(self, device: str, prop: str) -> PropertySetting: ...
    def getVerbose(self) -> str: ...
    def isConfigurationIncluded(self, cfg: Configuration) -> bool: ...
    def isPropertyIncluded(self, device: str, prop: str) -> bool: ...
    def isSettingIncluded(self, ps: PropertySetting) -> bool: ...
    def size(self) -> int: ...

class MetadataTag:
    def Clone(self) -> MetadataTag: ...
    def GetDevice(self) -> str: ...
    def GetName(self) -> str: ...
    def GetQualifiedName(self) -> str: ...
    def IsReadOnly(self) -> bool: ...
    def Restore(self, stream: str) -> bool: ...
    def Serialize(self) -> str: ...
    def SetDevice(self, device: str) -> None: ...
    def SetName(self, name: str) -> None: ...
    def SetReadOnly(self, ro: bool) -> None: ...
    def ToArrayTag(self) -> MetadataArrayTag: ...
    def ToSingleTag(self) -> MetadataSingleTag: ...

class MetadataArrayTag(MetadataTag):
    @overload
    def __init__(self): ...
    @overload
    def __init__(self, name: str, device: str, readOnly: bool): ...
    def AddValue(self, val: str): ...
    def GetSize(self) -> int: ...
    def GetValue(self) -> str: ...
    def SetValue(self, val: str, idx: int) -> str: ...

class MetadataSingleTag(MetadataTag):
    @overload
    def __init__(self): ...
    @overload
    def __init__(self, name: str, device: str, readOnly: bool): ...
    def GetValue(self) -> str: ...
    def SetValue(self, val: str) -> str: ...

class Metadata:
    def Clear(self) -> None: ...
    def Dump(self) -> str: ...
    def GetArrayTag(self, key: str) -> MetadataArrayTag: ...
    def GetKeys(self) -> str: ...
    def GetSingleTag(self, key: str) -> MetadataSingleTag: ...
    def HasTag(self, key: str) -> bool: ...
    def Merge(self, newTags: Metadata) -> None: ...
    def RemoveTag(self, key: str) -> None: ...
    def Restore(self, stream: str) -> bool: ...
    def Serialize(self) -> str: ...
    def SetTag(self, tag: MetadataTag) -> None: ...
    def readLine(self, iss) -> str: ...

class MetadataError:
    def __init__(self, err: str) -> None: ...
    def getMsg(self) -> str: ...

class MetadataIndexError(MetadataError): ...
class MetadataKeyError(MetadataError): ...

class MMEventCallback:
    def __init__(self) -> None: ...
    def onChannelGroupChanged(self, newChannelGroupName: str) -> None: ...
    def onConfigGroupChanged(self, groupName: str, newConfigName: str) -> None: ...
    def onExposureChanged(self, name: str, newExposure: float) -> None: ...
    def onPixelSizeAffineChanged(
        self, v0: float, v1: float, v2: float, v3: float, v4: float, v5: float
    ) -> None: ...
    def onPixelSizeChanged(self, newPixelSizeUm: float) -> None: ...
    def onPropertiesChanged(
        self,
    ) -> None: ...
    def onPropertyChanged(self, name: str, propName: str, propValue: str) -> None: ...
    def onSLMExposureChanged(self, name: str, newExposure: float) -> None: ...
    def onStagePositionChanged(self, name: str, pos: float) -> None: ...
    def onSystemConfigurationLoaded(
        self,
    ) -> None: ...
    def onXYStagePositionChanged(self, name: str, xpos: float, ypos: float) -> None: ...

class PropertyBlock:
    def __init__(self) -> None: ...
    def addPair(self, pair: PropertyPair) -> None: ...
    def getPair(self, index: int) -> PropertyPair: ...
    def getValue(self, key: str) -> str: ...
    def size(self) -> int: ...

class PropertyPair:
    @overload
    def __init__(self) -> None: ...
    @overload
    def __init__(self, prop: str, value: str) -> None: ...
    def getPropertyName(self) -> str: ...
    def getPropertyValue(self) -> str: ...

class PropertySetting:
    @overload
    def __init__(self) -> None: ...
    @overload
    def __init__(self, deviceLabel: str, prop: str, value: str) -> None: ...
    @overload
    def __init__(
        self, deviceLabel: str, prop: str, value: str, readOnly: bool
    ) -> None: ...
    @staticmethod
    def generateKey(self, device: str, prop: str) -> str: ...
    def getDeviceLabel(self) -> str: ...
    def getKey(self) -> str: ...
    def getPropertyName(self) -> str: ...
    def getPropertyValue(self) -> str: ...
    def getReadOnly(self) -> bool: ...
    def getVerbose(self) -> str: ...
    def isEqualTo(self, ps: PropertySetting) -> bool: ...
    def __eq__(sel, ps: PropertySetting) -> bool: ...
