from unittest.mock import Mock, call

import pytest

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
            call("Objective", "State", "3"),
            call("Objective", "Label", "Nikon 20X Plan Fluor ELWD"),
        ]
    )
    assert core.getState("Objective") == 3

    mock.reset_mock()
    assert core.getState("Dichroic") == 0
    core.setStateLabel("Dichroic", "Q505LP")
    mock.assert_has_calls(
        [call("Dichroic", "State", "1"), call("Dichroic", "Label", "Q505LP")]
    )
    assert core.getState("Dichroic") == 1


def test_set_statedevice_property_emits_events(core: CMMCorePlus):
    mock = Mock()
    core.events.propertyChanged.connect(mock)
    assert core.getState("Objective") == 1
    assert core.getProperty("Objective", "State") == "1"
    core.setProperty("Objective", "State", "3")
    mock.assert_has_calls(
        [
            call("Objective", "State", "3"),
            call("Objective", "Label", "Nikon 20X Plan Fluor ELWD"),
        ]
    )
    assert core.getState("Objective") == 3
    assert core.getProperty("Objective", "State") == "3"
    assert core.getProperty("Objective", "Label") == "Nikon 20X Plan Fluor ELWD"

    mock.reset_mock()
    assert core.getProperty("Dichroic", "Label") == "400DCLP"
    core.setProperty("Dichroic", "Label", "Q505LP")
    mock.assert_has_calls(
        [call("Dichroic", "State", "1"), call("Dichroic", "Label", "Q505LP")]
    )
    assert core.getProperty("Dichroic", "Label") == "Q505LP"
    assert core.getProperty("Dichroic", "State") == "1"
