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
        if not isinstance(m, value):
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

    core.events.startContinuousSequenceAcquisition.connect(mock1)
    core.events.stopSequenceAcquisition.connect(mock2)
    core.events.startSequenceAcquisition.connect(mock3)

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
    core.events.shutterSet.connect(mock)
    core.setShutterOpen("Shutter", True)
    mock.assert_has_calls(
        [
            call("Shutter", True),
        ]
    )
    assert core.getShutterOpen("Shutter")


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
