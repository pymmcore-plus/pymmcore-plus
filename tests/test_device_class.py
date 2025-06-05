from unittest.mock import Mock

import pytest

from pymmcore_plus import CMMCorePlus, Device, DeviceDetectionStatus, DeviceType
from pymmcore_plus import core as _core
from pymmcore_plus.core._constants import FocusDirection
from pymmcore_plus.core._property import DeviceProperty


def test_device_object(core: CMMCorePlus) -> None:
    for device in core.iterDevices(as_object=True):
        device.wait()
        assert not device.isBusy()
        assert device.schema()
        assert isinstance(device.schema(), dict)
        assert device.description()
        assert isinstance(device.description(), str)
        lib = device.library()
        assert lib if device.type() is not DeviceType.Core else not lib
        assert device.name()
        assert repr(device)
        assert device.core is core
        assert device.isLoaded()
        assert isinstance(device.usesDelay(), bool)
        if device.usesDelay():
            device.setDelayMs(0.1)
            assert device.delayMs() == 0.1

        assert all(isinstance(prop, DeviceProperty) for prop in device.properties)

        if device.supportsDetection():
            assert device.detect() is not DeviceDetectionStatus.Unimplemented
        else:
            assert device.detect() is DeviceDetectionStatus.Unimplemented

        if device.type() is not DeviceType.Core:
            device.unload()
            assert not device.isLoaded()
            assert "NOT LOADED" in repr(device)

        assert repr(device)


def test_device_load_errors(core: CMMCorePlus) -> None:
    dev = Device("Something", core)

    with pytest.raises(RuntimeError) as e:
        dev.load("NotAnAdapter", "prop")
    assert ("Adapter name 'NotAnAdapter' not in list of known") in str(e.value)

    with pytest.raises(RuntimeError) as e:
        dev.load("DemoCamera", "...")
    assert ("'...' not in devices provided by adapter 'DemoCamera'") in str(e.value)

    dev.load("DemoCamera", "DCam")

    with pytest.warns(UserWarning):
        dev.load("DemoCamera", "DCam")

    with pytest.raises(ValueError, match="has no property"):
        dev.getPropertyObject("NotAProperty")


def test_device_object_wrong_type(core: CMMCorePlus) -> None:
    with pytest.raises(TypeError, match="requested but device"):
        core.getDeviceObject("Camera", DeviceType.XYStage)


def test_device_callbacks(core: CMMCorePlus) -> None:
    dev = Device("Camera", core)
    mock = Mock()
    mock2 = Mock()

    # regular connection
    dev.propertyChanged.connect(mock)
    dev.propertyChanged("Gain").connect(mock2)
    core.setProperty("Camera", "Gain", "6")
    mock.assert_called_once_with("Gain", "6")
    mock2.assert_called_once_with("6")
    mock.reset_mock()
    mock2.reset_mock()
    core.setProperty("Camera", "Binning", "2")
    mock.assert_called_once_with("Binning", "2")
    mock2.assert_not_called()

    # regular disconnection
    mock.reset_mock()
    mock2.reset_mock()
    dev.propertyChanged.disconnect(mock)
    dev.propertyChanged("Gain").disconnect(mock2)
    core.setProperty("Camera", "Gain", "4")
    mock.assert_not_called()
    mock2.assert_not_called()


DEV_TYPES: dict[str, DeviceType] = {
    "Camera": DeviceType.Camera,
    "Emission": DeviceType.State,
    "Z": DeviceType.Stage,
    "XY": DeviceType.XYStage,
    "LED Shutter": DeviceType.Shutter,
    "Autofocus": DeviceType.AutoFocus,
    "Core": DeviceType.Core,
    "DHub": DeviceType.Hub,
}


@pytest.mark.parametrize("label, dev_type", DEV_TYPES.items())
def test_device_sub_types(core: CMMCorePlus, label: str, dev_type: DeviceType) -> None:
    device = core.getDeviceObject(label, dev_type)
    assert device.type() is dev_type

    # note, some of these tests are specific to the exact label being used
    if device.type() is DeviceType.Camera:
        assert isinstance(device, _core.CameraDevice)
        device.setROI(0, 0, 10, 10)
        assert tuple(device.getROI()) == (0, 0, 10, 10)
        device.setExposure(42)
        assert device.getExposure() == 42
        device.exposure = 12
        assert device.exposure == 12
        assert not device.isSequenceable()
        assert not device.isSequenceRunning()
        assert device.getParentLabel() == "DHub"
    elif device.type() is DeviceType.XYStage:
        assert isinstance(device, _core.XYStageDevice)
        device.setXYPosition(10, 10)
        device.wait()
        assert tuple(round(x) for x in device.getXYPosition()) == (10, 10)
        device.position = (20, 30)
        device.wait()
        assert tuple(round(x) for x in device.position) == (20, 30)
        device.setRelativeXYPosition(1, 1)
        device.wait()
        assert tuple(round(x) for x in device.getXYPosition()) == (21, 31)
        assert round(device.getXPosition()) == 21
        assert round(device.getYPosition()) == 31
        device.setOriginXY()
        device.setOrigin()
        device.setAdapterOriginXY(2, 2)
        assert not device.isXYStageSequenceable()
        assert not device.isSequenceable()

    elif device.type() is DeviceType.Stage:
        assert isinstance(device, _core.StageDevice)
        device.setPosition(10)
        assert device.getPosition() == 10
        device.position = 1
        assert device.position == 1
        device.setRelativePosition(1)
        assert device.getPosition() == 2
        device.setOrigin()
        try:
            device.setAdapterOrigin(2)
        except RuntimeError:
            pass
        device.setFocusDirection(10)
        assert device.getFocusDirection() is FocusDirection.TowardSample
        device.setFocusDirection(-1)
        assert device.getFocusDirection() is FocusDirection.AwayFromSample
        assert not device.isContinuousFocusDrive()
        assert not device.isStageLinearSequenceable()
        assert not device.isStageSequenceable()
        assert not device.isSequenceable()
        device.wait()
        device.stop()
    elif device.type() is DeviceType.Shutter:
        assert isinstance(device, _core.ShutterDevice)
        device.open()
        assert device.isOpen()
        device.close()
        assert not device.isOpen()
    elif device.type() is DeviceType.State:
        assert isinstance(device, _core.StateDevice)
        device.state = 2
        assert device.state == 2
        device.setState(1)
        assert device.getState() == 1
        assert device.getNumberOfStates() == 10
        device.setStateLabel("Chroma-D460")
        assert device.getStateLabel() == "Chroma-D460"
        device.defineStateLabel(0, "MyState")
        device.state = 0
        assert device.getStateLabel() == "MyState"
        assert "MyState" in device.getStateLabels()
        assert device.getStateFromLabel("MyState") == 0
    elif device.type() is DeviceType.AutoFocus:
        assert isinstance(device, _core.AutoFocusDevice)
    elif device.type() is DeviceType.Core:
        assert isinstance(device, _core.CoreDevice)
    elif device.type() is DeviceType.Hub:
        assert isinstance(device, _core.HubDevice)
        assert "DWheel" in device.getInstalledDevices()
        assert isinstance(device.getInstalledDeviceDescription("DCam"), str)
        assert "Camera" in device.getLoadedPeripheralDevices()
    # ------------------------------
    # these aren't actually tested with the test config
    elif device.type() is DeviceType.SLM:
        assert isinstance(device, _core.SLMDevice)
    elif device.type() is DeviceType.SignalIO:
        assert isinstance(device, _core.SignalIODevice)
    elif device.type() is DeviceType.Generic:
        assert isinstance(device, _core.GenericDevice)
    elif device.type() is DeviceType.Magnifier:
        assert isinstance(device, _core.MagnifierDevice)
    elif device.type() is DeviceType.Galvo:
        assert isinstance(device, _core.GalvoDevice)
    elif device.type() is DeviceType.ImageProcessor:
        assert isinstance(device, _core.ImageProcessorDevice)
    elif device.type() is DeviceType.Serial:
        assert isinstance(device, _core.SerialDevice)
    # --------------------------------


def test_device_errors(core: CMMCorePlus) -> None:
    assert not isinstance(Device("Camera", core), _core.CameraDevice)

    cam = _core.CameraDevice("Camera", core)
    assert isinstance(cam, _core.CameraDevice)
    assert cam.isLoaded()
    with pytest.raises(RuntimeError, match="Cannot change label"):
        cam.label = "Camera2"

    assert isinstance(_core.Device.create("Camera", core), _core.CameraDevice)
    with pytest.raises(TypeError, match="Cannot cast"):
        _core.StageDevice.create("Camera", core)

    with pytest.raises(RuntimeError, match="No device with label"):
        _core.StageDevice.create("NotExist", core)

    # wrong type
    with pytest.raises(TypeError, match="Cannot create loaded device with label "):
        _core.StageDevice("Camera", core)
