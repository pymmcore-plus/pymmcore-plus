from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import Mock, call

import pytest

from pymmcore_plus import CMMCorePlus, Keyword
from pymmcore_plus._util import PYMM_SIGNALS_BACKEND
from pymmcore_plus.core.events import CMMCoreSignaler, PCoreSignaler
from pymmcore_plus.core.events._protocol import PSignal, PSignalInstance

Signalers = [CMMCoreSignaler]
try:
    from pymmcore_plus.core.events import QCoreSignaler

    Signalers.append(QCoreSignaler)
except ImportError:
    QCoreSignaler = None  # type: ignore


PARAMS = [
    ("psygnal", CMMCoreSignaler),
    ("qt", Signalers[-1]),
    ("nonsense", Signalers[-1]),
    ("auto", Signalers[-1]),
]


@pytest.mark.parametrize("env_var, expect", PARAMS)
def test_signal_backend_selection(
    env_var: str,
    expect: type[PCoreSignaler],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if expect == QCoreSignaler and QCoreSignaler is not None:
        from qtpy.QtWidgets import QApplication

        _ = QApplication.instance() or QApplication([])

    monkeypatch.setenv(PYMM_SIGNALS_BACKEND, env_var)
    ctx = (
        pytest.warns(UserWarning)
        if (env_var == "nonsense" or (env_var == "qt" and QCoreSignaler is None))
        else nullcontext()
    )
    with ctx:
        core = CMMCorePlus()
    assert isinstance(core.events, expect)


@pytest.mark.parametrize("cls", Signalers)
def test_events_protocols(cls):
    obj = cls()
    name = cls.__name__
    if not isinstance(obj, PCoreSignaler):
        required = set(PCoreSignaler.__annotations__)
        raise AssertionError(
            f"{name!r} does not implement the CoreSignaler Protocol. "
            f"Missing attributes: {required - set(dir(obj))!r}"
        )
    for attr in PCoreSignaler.__annotations__:
        m = getattr(obj, attr)
        if not isinstance(m, (PSignal, PSignalInstance)):
            raise AssertionError(
                f"'{name}.{attr}' expected type "
                f"{(PSignal, PSignalInstance)!r}, got {type(m)}"
            )


def test_set_property_events(core: CMMCorePlus) -> None:
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


def test_set_state_events(core: CMMCorePlus) -> None:
    mock = Mock()
    core.events.propertyChanged.connect(mock)
    assert core.getState("Objective") == 1
    core.setState("Objective", 3)
    mock.assert_has_calls(
        [
            call("Objective", Keyword.State.value, "3"),
            call("Objective", Keyword.Label.value, "Nikon 20X Plan Fluor ELWD"),
        ]
    )
    assert core.getState("Objective") == 3

    mock.reset_mock()
    assert core.getState("Dichroic") == 0
    core.setStateLabel("Dichroic", "Q505LP")
    mock.assert_has_calls(
        [
            call("Dichroic", Keyword.State.value, "1"),
            call("Dichroic", Keyword.Label.value, "Q505LP"),
        ]
    )
    assert core.getState("Dichroic") == 1


def test_set_statedevice_property_emits_events(core: CMMCorePlus) -> None:
    mock = Mock()
    core.events.propertyChanged.connect(mock)
    assert core.getState("Objective") == 1
    assert core.getProperty("Objective", Keyword.State.value) == "1"
    core.setProperty("Objective", Keyword.State.value, "3")
    mock.assert_has_calls(
        [
            call("Objective", Keyword.State.value, "3"),
            call("Objective", Keyword.Label.value, "Nikon 20X Plan Fluor ELWD"),
        ]
    )
    assert core.getState("Objective") == 3
    assert core.getProperty("Objective", Keyword.State.value) == "3"
    assert (
        core.getProperty("Objective", Keyword.Label.value)
        == "Nikon 20X Plan Fluor ELWD"
    )

    mock.reset_mock()
    assert core.getProperty("Dichroic", Keyword.Label.value) == "400DCLP"
    core.setProperty("Dichroic", Keyword.Label.value, "Q505LP")
    mock.assert_has_calls(
        [
            call("Dichroic", Keyword.State.value, "1"),
            call("Dichroic", Keyword.Label.value, "Q505LP"),
        ]
    )
    assert core.getProperty("Dichroic", Keyword.Label.value) == "Q505LP"
    assert core.getProperty("Dichroic", Keyword.State.value) == "1"


def test_device_property_events(core: CMMCorePlus) -> None:
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


def test_sequence_acquisition_events(core: CMMCorePlus) -> None:
    mock1a = Mock()
    mock1b = Mock()
    mock2a = Mock()
    mock2b = Mock()
    mock3 = Mock()

    core.events.continuousSequenceAcquisitionStarting.connect(mock1a)
    core.events.continuousSequenceAcquisitionStarted.connect(mock1b)
    core.events.sequenceAcquisitionStarting.connect(mock2a)
    core.events.sequenceAcquisitionStarted.connect(mock2b)
    core.events.sequenceAcquisitionStopped.connect(mock3)

    core.startContinuousSequenceAcquisition()
    mock1a.assert_called_once()
    mock1b.assert_called_once()

    core.stopSequenceAcquisition()
    mock3.assert_any_call(core.getCameraDevice())

    # without camera label
    core.startSequenceAcquisition(5, 100.0, True)
    mock2a.assert_any_call(core.getCameraDevice())
    mock2b.assert_any_call(core.getCameraDevice())
    core.stopSequenceAcquisition()
    mock3.assert_any_call(core.getCameraDevice())

    # with camera label
    cam = core.getCameraDevice()
    core.startSequenceAcquisition(cam, 5, 100.0, True)
    mock2a.assert_any_call(cam)
    mock2b.assert_any_call(cam)
    core.stopSequenceAcquisition(cam)
    mock3.assert_any_call(cam)


def test_shutter_device_events(core: CMMCorePlus) -> None:
    mock = Mock()
    core.events.propertyChanged.connect(mock)
    core.setShutterOpen("White Light Shutter", True)
    mock.assert_called_once_with("White Light Shutter", Keyword.State.value, "1")
    assert core.getShutterOpen("White Light Shutter")
    assert core.getProperty("White Light Shutter", Keyword.State.value) == "1"


def test_autoshutter_device_events(core: CMMCorePlus) -> None:
    mock = Mock()
    core.events.autoShutterSet.connect(mock)
    core.setAutoShutter(True)
    mock.assert_called_once_with(True)
    assert core.getAutoShutter()


def test_groups_and_presets_events(core: CMMCorePlus) -> None:
    cfg_deleted = Mock()
    core.events.configDeleted.connect(cfg_deleted)
    core.deleteConfig("Camera", "HighRes")
    cfg_deleted.assert_called_once_with("Camera", "HighRes")
    assert "HighRes" not in core.getAvailableConfigs("Camera")

    grp_deleted = Mock()
    core.events.configGroupDeleted.connect(grp_deleted)
    core.deleteConfigGroup("Objective")
    grp_deleted.assert_called_once_with("Objective")
    assert "Objective" not in core.getAvailableConfigGroups()

    cfg_defined = Mock()
    core.events.configDefined.connect(cfg_defined)
    core.defineConfig("NewGroup", "")
    cfg_defined.assert_called_once_with("NewGroup", "NewPreset", "", "", "")
    assert "NewGroup" in core.getAvailableConfigGroups()
    assert "NewPreset" in core.getAvailableConfigs("NewGroup")

    cfg_defined.reset_mock()
    core.defineConfig("NewGroup_1", "New")
    cfg_defined.assert_called_once_with("NewGroup_1", "New", "", "", "")
    assert "NewGroup_1" in core.getAvailableConfigGroups()
    assert "New" in core.getAvailableConfigs("NewGroup_1")

    cfg_defined.reset_mock()
    core.defineConfig("NewGroup_2", "New", "Dichroic", "Label", "Q505LP")
    cfg_defined.assert_called_once_with(
        "NewGroup_2", "New", "Dichroic", "Label", "Q505LP"
    )
    assert "NewGroup_2" in core.getAvailableConfigGroups()
    assert "New" in core.getAvailableConfigs("NewGroup_2")
    dpv = [(k[0], k[1], k[2]) for k in core.getConfigData("NewGroup_2", "New")]
    assert ("Dichroic", "Label", "Q505LP") in dpv


def test_set_camera_roi_event(core: CMMCorePlus) -> None:
    mock = Mock()
    core.events.roiSet.connect(mock)
    core.setROI(10, 20, 100, 200)
    mock.assert_called_once_with(core.getCameraDevice(), 10, 20, 100, 200)
    assert list(core.getROI()) == [10, 20, 100, 200]


def test_pixel_changed_event(core: CMMCorePlus) -> None:
    mock = Mock()
    core.events.pixelSizeChanged.connect(mock)

    core.deletePixelSizeConfig("Res10x")
    mock.assert_called_once_with(0.0)
    assert "Res10x" not in core.getAvailablePixelSizeConfigs()

    core.definePixelSizeConfig("test", "Objective", "Label", "Nikon 10X S Fluor")
    mock.assert_any_call(0.0)
    assert "test" in core.getAvailablePixelSizeConfigs()

    core.setPixelSizeUm("test", 6.5)
    mock.assert_any_call(6.5)
    assert core.getPixelSizeUmByID("test") == 6.5


def test_set_channelgroup(core: CMMCorePlus) -> None:
    mock = Mock()
    core.events.channelGroupChanged.connect(mock)

    core.setChannelGroup("Camera")
    assert core.getChannelGroup() == "Camera"
    mock.assert_any_call("Camera")


def test_set_focus_device(core: CMMCorePlus) -> None:
    mock = Mock()
    core.events.propertyChanged.connect(mock)

    core.setFocusDevice("")
    assert not core.getFocusDevice()
    mock.assert_called_once_with("Core", "Focus", "")

    core.setFocusDevice("Z")
    assert core.getFocusDevice() == "Z"
    mock.assert_any_call("Core", "Focus", "Z")


SIGNATURES: list[tuple[str, tuple[type, ...]]] = [
    ("propertiesChanged", ()),
    ("propertyChanged", (str, str, str)),
    ("channelGroupChanged", (str,)),
    ("configGroupChanged", (str, str)),
    ("systemConfigurationLoaded", ()),
    ("pixelSizeChanged", (float,)),
    ("pixelSizeAffineChanged", (float, float, float, float, float, float)),
    ("stagePositionChanged", (str, float)),
    ("XYStagePositionChanged", (str, float, float)),
    ("exposureChanged", (str, float)),
    ("SLMExposureChanged", (str, float)),
    ("configSet", (str, str)),
    ("imageSnapped", (str,)),
    ("mdaEngineRegistered", (object, object)),
    ("continuousSequenceAcquisitionStarting", ()),
    ("continuousSequenceAcquisitionStarted", ()),
    ("sequenceAcquisitionStarting", (str,)),  # NEW
    ("sequenceAcquisitionStarted", (str,)),  # NEW
    ("sequenceAcquisitionStopped", (str,)),
    ("autoShutterSet", (bool,)),
    ("configGroupDeleted", (str,)),
    ("configDeleted", (str, str)),
    ("configDefined", (str, str, str, str, str)),
    ("roiSet", (str, int, int, int, int)),
]


@pytest.mark.parametrize("name, signature", SIGNATURES)
def test_event_signatures(
    core: CMMCorePlus, name: str, signature: tuple[type, ...]
) -> None:
    """Test connecting to events with expected signatures."""
    # create callback expecting the exact number of arguments in signature
    num_args = len(signature)
    sig_str = ", ".join(f"a{i}" for i in range(num_args))
    ns: dict = {}

    exec(f"def func({sig_str}): ...", ns)
    full_func = ns["func"]
    assert callable(full_func), "Function is not callable"

    signal = getattr(core.events, name)
    assert isinstance(signal, PSignalInstance)
    signal.connect(full_func)
    signal.emit(*[t() for t in signature])  # emit with dummy values

    # min-func
    signal.disconnect(full_func)
    signal.connect(lambda: None)
    signal.emit(*[t() for t in signature])  # emit with dummy values


DEPRECATED_SIGNATURES: list[tuple[str, tuple[type, ...], tuple[type, ...]]] = [
    ("sequenceAcquisitionStarting", (str,), (str, int, float, bool)),  # DEPRECATED
    ("sequenceAcquisitionStarted", (str,), (str, int, float, bool)),  # DEPRECATED
]


@pytest.mark.parametrize("name, new, old", DEPRECATED_SIGNATURES)
def test_deprecated_event_signatures(
    core: CMMCorePlus, name: str, new: tuple[type, ...], old: tuple[type, ...]
) -> None:
    """Test connecting to events with expected signatures."""
    # create callback expecting the exact number of arguments in signature
    num_args = len(old)
    sig_str = ", ".join(f"a{i}" for i in range(num_args))
    ns: dict = {}

    exec(f"def func({sig_str}): ...", ns)
    full_func = ns["func"]
    assert callable(full_func), "Function is not callable"

    signal = getattr(core.events, name)
    assert isinstance(signal, PSignalInstance)
    with pytest.warns(FutureWarning, match="Callback 'func' requires"):
        signal.connect(full_func)

    signal.emit(*[t() for t in new])  # emit with dummy values
