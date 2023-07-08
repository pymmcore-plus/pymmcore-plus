from typing import get_args
from unittest.mock import Mock, call

import pytest
from pymmcore import g_Keyword_Label as LABEL
from pymmcore import g_Keyword_State as STATE
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.core.events import CMMCoreSignaler, PCoreSignaler, QCoreSignaler


@pytest.mark.parametrize("cls", [CMMCoreSignaler, QCoreSignaler])
def test_events_protocols(cls):
    obj = cls()
    name = cls.__name__
    if not isinstance(obj, PCoreSignaler):
        required = set(PCoreSignaler.__annotations__)
        raise AssertionError(
            f"{name!r} does not implement the CoreSignaler Protocol. "
            f"Missing attributes: {required - set(dir(obj))!r}"
        )
    for attr, value in PCoreSignaler.__annotations__.items():
        m = getattr(obj, attr)
        if not isinstance(m, get_args(value) or value):
            raise AssertionError(
                f"'{name}.{attr}' expected type {value.__name__!r}, got {type(m)}"
            )


def test_set_property_events(core: CMMCorePlus):
    """Test that using setProperty always emits a propertyChanged event."""
    mock = Mock()
    core.events.propertyChanged.connect(mock)
    core.setProperty("Camera", "Binning", "2")
    mock.assert_called_once_with("Camera", "Binning", "2")

    mock.reset_mock()
    core.setProperty("Camera", "Binning", "1")
    mock.assert_called_once_with("Camera", "Binning", "1")

    mock.reset_mock()
    core.setProperty("Camera", "Binning", "1")
    mock.assert_not_called()  # value didn't change

    # this is not a property that the DemoCamera emits...
    # so with regular pymmcore, this would not be emitted.
    core.setProperty("Camera", "AllowMultiROI", "1")
    mock.assert_called_once_with("Camera", "AllowMultiROI", "1")


def test_set_state_events(core: CMMCorePlus):
    mock = Mock()
    core.events.propertyChanged.connect(mock)
    assert core.getState("Objective") == 1
    core.setState("Objective", 3)
    mock.assert_has_calls(
        [
            call("Objective", STATE, "3"),
            call("Objective", LABEL, "Nikon 20X Plan Fluor ELWD"),
        ]
    )
    assert core.getState("Objective") == 3

    mock.reset_mock()
    assert core.getState("Dichroic") == 0
    core.setStateLabel("Dichroic", "Q505LP")
    mock.assert_has_calls(
        [call("Dichroic", STATE, "1"), call("Dichroic", LABEL, "Q505LP")]
    )
    assert core.getState("Dichroic") == 1


def test_set_statedevice_property_emits_events(core: CMMCorePlus):
    mock = Mock()
    core.events.propertyChanged.connect(mock)
    assert core.getState("Objective") == 1
    assert core.getProperty("Objective", STATE) == "1"
    core.setProperty("Objective", STATE, "3")
    mock.assert_has_calls(
        [
            call("Objective", STATE, "3"),
            call("Objective", LABEL, "Nikon 20X Plan Fluor ELWD"),
        ]
    )
    assert core.getState("Objective") == 3
    assert core.getProperty("Objective", STATE) == "3"
    assert core.getProperty("Objective", LABEL) == "Nikon 20X Plan Fluor ELWD"

    mock.reset_mock()
    assert core.getProperty("Dichroic", LABEL) == "400DCLP"
    core.setProperty("Dichroic", LABEL, "Q505LP")
    mock.assert_has_calls(
        [call("Dichroic", STATE, "1"), call("Dichroic", LABEL, "Q505LP")]
    )
    assert core.getProperty("Dichroic", LABEL) == "Q505LP"
    assert core.getProperty("Dichroic", STATE) == "1"


def test_device_property_events(core: CMMCorePlus):
    mock1 = Mock()
    mock2 = Mock()
    core.events.devicePropertyChanged("Camera", "Gain").connect(mock1)
    core.events.devicePropertyChanged("Camera").connect(mock2)

    core.setProperty("Camera", "Gain", "6")
    mock1.assert_called_once_with("6")
    mock2.assert_called_once_with("Gain", "6")

    mock1.reset_mock()
    mock2.reset_mock()
    core.setProperty("Camera", "Binning", "2")
    mock1.assert_not_called()
    mock2.assert_called_once_with("Binning", "2")

    mock1.reset_mock()
    mock2.reset_mock()
    core.events.devicePropertyChanged("Camera", "Gain").disconnect(mock1)
    core.events.devicePropertyChanged("Camera").disconnect(mock2)
    core.setProperty("Camera", "Gain", "5")
    mock1.assert_not_called()
    mock2.assert_not_called()


def test_sequence_acquisition_events(core: CMMCorePlus):
    mock1 = Mock()
    mock2 = Mock()
    mock3 = Mock()

    core.events.continuousSequenceAcquisitionStarted.connect(mock1)
    core.events.sequenceAcquisitionStopped.connect(mock2)
    core.events.sequenceAcquisitionStarted.connect(mock3)

    core.startContinuousSequenceAcquisition()
    mock1.assert_has_calls(
        [
            call(),
        ]
    )

    core.stopSequenceAcquisition()
    mock2.assert_has_calls(
        [
            call(core.getCameraDevice()),
        ]
    )

    # without camera label
    core.startSequenceAcquisition(5, 100.0, True)
    mock3.assert_has_calls(
        [
            call(core.getCameraDevice(), 5, 100.0, True),
        ]
    )
    core.stopSequenceAcquisition()
    mock2.assert_has_calls(
        [
            call(core.getCameraDevice()),
        ]
    )

    # with camera label
    cam = core.getCameraDevice()
    core.startSequenceAcquisition(cam, 5, 100.0, True)
    mock3.assert_has_calls(
        [
            call(cam, 5, 100.0, True),
        ]
    )
    core.stopSequenceAcquisition(cam)
    mock2.assert_has_calls(
        [
            call(cam),
        ]
    )


def test_shutter_device_events(core: CMMCorePlus):
    mock = Mock()
    core.events.propertyChanged.connect(mock)
    core.setShutterOpen("White Light Shutter", True)
    mock.assert_has_calls(
        [
            call("White Light Shutter", STATE, True),
        ]
    )
    assert core.getShutterOpen("White Light Shutter")
    assert core.getProperty("White Light Shutter", STATE) == "1"


def test_autoshutter_device_events(core: CMMCorePlus):
    mock = Mock()
    core.events.autoShutterSet.connect(mock)
    core.setAutoShutter(True)
    mock.assert_has_calls(
        [
            call(True),
        ]
    )
    assert core.getAutoShutter()


def test_groups_and_presets_events(core: CMMCorePlus):
    mock = Mock()
    core.events.configDeleted.connect(mock)
    core.deleteConfig("Camera", "HighRes")
    mock.assert_has_calls(
        [
            call("Camera", "HighRes"),
        ]
    )
    assert "HighRes" not in core.getAvailableConfigs("Camera")

    mock = Mock()
    core.events.configGroupDeleted.connect(mock)
    core.deleteConfigGroup("Objective")
    mock.assert_has_calls(
        [
            call("Objective"),
        ]
    )
    assert "Objective" not in core.getAvailableConfigGroups()

    mock = Mock()
    core.events.configDefined.connect(mock)
    core.defineConfig("NewGroup", "")
    mock.assert_has_calls(
        [
            call("NewGroup", "NewPreset", "", "", ""),
        ]
    )
    assert "NewGroup" in core.getAvailableConfigGroups()
    assert "NewPreset" in core.getAvailableConfigs("NewGroup")

    mock = Mock()
    core.events.configDefined.connect(mock)
    core.defineConfig("NewGroup_1", "New")
    mock.assert_has_calls(
        [
            call("NewGroup_1", "New", "", "", ""),
        ]
    )
    assert "NewGroup_1" in core.getAvailableConfigGroups()
    assert "New" in core.getAvailableConfigs("NewGroup_1")

    mock = Mock()
    core.events.configDefined.connect(mock)
    core.defineConfig("NewGroup_2", "New", "Dichroic", "Label", "Q505LP")
    mock.assert_has_calls(
        [
            call("NewGroup_2", "New", "Dichroic", "Label", "Q505LP"),
        ]
    )
    assert "NewGroup_2" in core.getAvailableConfigGroups()
    assert "New" in core.getAvailableConfigs("NewGroup_2")
    dpv = [(k[0], k[1], k[2]) for k in core.getConfigData("NewGroup_2", "New")]
    assert ("Dichroic", "Label", "Q505LP") in dpv


def test_set_camera_roi_event(core: CMMCorePlus):
    mock = Mock()
    core.events.roiSet.connect(mock)
    core.setROI(10, 20, 100, 200)
    mock.assert_has_calls(
        [
            call(core.getCameraDevice(), 10, 20, 100, 200),
        ]
    )
    assert list(core.getROI()) == [10, 20, 100, 200]


def test_pixel_changed_event(core: CMMCorePlus):
    mock = Mock()
    core.events.pixelSizeChanged.connect(mock)

    core.deletePixelSizeConfig("Res10x")
    mock.assert_has_calls([call(0.0)])
    assert "Res10x" not in core.getAvailablePixelSizeConfigs()

    core.definePixelSizeConfig("test", "Objective", "Label", "Nikon 10X S Fluor")
    mock.assert_has_calls([call(0.0)])
    assert "test" in core.getAvailablePixelSizeConfigs()

    core.setPixelSizeUm("test", 6.5)
    mock.assert_has_calls([call(6.5)])
    assert core.getPixelSizeUmByID("test") == 6.5


def test_set_channelgroup(core: CMMCorePlus):
    mock = Mock()
    core.events.channelGroupChanged.connect(mock)

    core.setChannelGroup("Camera")
    assert core.getChannelGroup() == "Camera"
    mock.assert_has_calls([call("Camera")])


def test_set_focus_device(core: CMMCorePlus):
    mock = Mock()
    core.events.propertyChanged.connect(mock)

    core.setFocusDevice("")
    assert not core.getFocusDevice()
    mock.assert_has_calls([call("Core", "Focus", "")])

    core.setFocusDevice("Z")
    assert core.getFocusDevice() == "Z"
    mock.assert_has_calls([call("Core", "Focus", "Z")])
