from dataclasses import dataclass
from typing import (
    Annotated,
    Any,
    Callable,
    Literal,
    Mapping,
    TypeVar,
    get_args,
    overload,
)

from fieldz import fields
from msgspec import Struct
from pymmcore import CMMCore
from pymmcore_plus import CMMCorePlus
from rich import print


@dataclass
class CoreMeta:
    func: Callable[[CMMCorePlus], Any]


BitDepth = Annotated[int, CoreMeta(CMMCore.getImageBitDepth)]


class Thing(Struct):
    bit_depth: BitDepth


getters = {}
for f in fields(Thing):
    if f.annotated_type:
        for meta in get_args(f.annotated_type):
            if isinstance(meta, CoreMeta):
                getters[f.name] = meta.func

core = CMMCorePlus()
core.loadSystemConfiguration()

T = TypeVar("T")


@overload
def make_getter(
    mapping: Mapping[str, Callable[[CMMCorePlus], Any]],
    cls: Literal[None] = ...,
) -> Callable[[CMMCorePlus], dict]: ...
@overload
def make_getter(
    mapping: Mapping[str, Callable[[CMMCorePlus], Any]],
    cls: Callable[..., T],
) -> Callable[[CMMCorePlus], T]: ...
def make_getter(
    mapping: Mapping[str, Callable[[CMMCorePlus], Any]],
    cls: Callable[..., T] | None = None,
) -> Callable[[CMMCorePlus], T | dict]:
    """Docstring."""

    def getter(core: CMMCorePlus) -> dict:
        data = {}
        for key, func in mapping.items():
            try:
                data[key] = func(core)
            except Exception as e:
                data[key] = e
        if cls is not None:
            return cls(**data)
        return data

    return getter


print(make_getter(getters, Thing)(core))

APIVersionInfo = Annotated[..., (CMMCore.getAPIVersionInfo)]
AutoFocusDevice = Annotated[..., (CMMCore.getAutoFocusDevice)]
AutoFocusOffset = Annotated[..., (CMMCore.getAutoFocusOffset)]
AutoShutter = Annotated[..., (CMMCore.getAutoShutter)]
AvailableConfigGroups = Annotated[..., (CMMCore.getAvailableConfigGroups)]
AvailablePixelSizeConfigs = Annotated[..., (CMMCore.getAvailablePixelSizeConfigs)]
BufferFreeCapacity = Annotated[..., (CMMCore.getBufferFreeCapacity)]
BufferTotalCapacity = Annotated[..., (CMMCore.getBufferTotalCapacity)]
BytesPerPixel = Annotated[..., (CMMCore.getBytesPerPixel)]
CameraDevice = Annotated[..., (CMMCore.getCameraDevice)]
ChannelGroup = Annotated[..., (CMMCore.getChannelGroup)]
CircularBufferMemoryFootprint = Annotated[
    ..., (CMMCore.getCircularBufferMemoryFootprint)
]
CurrentFocusScore = Annotated[..., (CMMCore.getCurrentFocusScore)]
CurrentPixelSizeConfig = Annotated[..., (CMMCore.getCurrentPixelSizeConfig)]
DeviceAdapterNames = Annotated[..., (CMMCore.getDeviceAdapterNames)]
DeviceAdapterSearchPaths = Annotated[..., (CMMCore.getDeviceAdapterSearchPaths)]
Exposure = Annotated[..., (CMMCore.getExposure)]
FocusDevice = Annotated[..., (CMMCore.getFocusDevice)]
GalvoDevice = Annotated[..., (CMMCore.getGalvoDevice)]
Image = Annotated[..., (CMMCore.getImage)]
ImageBitDepth = Annotated[..., (CMMCore.getImageBitDepth)]
ImageBufferSize = Annotated[..., (CMMCore.getImageBufferSize)]
ImageHeight = Annotated[..., (CMMCore.getImageHeight)]
ImageProcessorDevice = Annotated[..., (CMMCore.getImageProcessorDevice)]
ImageWidth = Annotated[..., (CMMCore.getImageWidth)]
LastFocusScore = Annotated[..., (CMMCore.getLastFocusScore)]
LastImage = Annotated[..., (CMMCore.getLastImage)]
LoadedDevices = Annotated[..., (CMMCore.getLoadedDevices)]
MagnificationFactor = Annotated[..., (CMMCore.getMagnificationFactor)]
MultiROI = Annotated[..., (CMMCore.getMultiROI)]
NumberOfCameraChannels = Annotated[..., (CMMCore.getNumberOfCameraChannels)]
NumberOfComponents = Annotated[..., (CMMCore.getNumberOfComponents)]
PixelSizeAffine = Annotated[..., (CMMCore.getPixelSizeAffine)]
PixelSizeUm = Annotated[..., (CMMCore.getPixelSizeUm)]
Position = Annotated[..., (CMMCore.getPosition)]
PrimaryLogFile = Annotated[..., (CMMCore.getPrimaryLogFile)]
RemainingImageCount = Annotated[..., (CMMCore.getRemainingImageCount)]
ROI = Annotated[..., (CMMCore.getROI)]
ShutterDevice = Annotated[..., (CMMCore.getShutterDevice)]
ShutterOpen = Annotated[..., (CMMCore.getShutterOpen)]
SLMDevice = Annotated[..., (CMMCore.getSLMDevice)]
SystemState = Annotated[..., (CMMCore.getSystemState)]
SystemStateCache = Annotated[..., (CMMCore.getSystemStateCache)]
TimeoutMs = Annotated[..., (CMMCore.getTimeoutMs)]
VersionInfo = Annotated[..., (CMMCore.getVersionInfo)]
XPosition = Annotated[..., (CMMCore.getXPosition)]
XYStageDevice = Annotated[..., (CMMCore.getXYStageDevice)]
YPosition = Annotated[..., (CMMCore.getYPosition)]
