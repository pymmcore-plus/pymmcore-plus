import json
import os
from unittest.mock import MagicMock, call

import numpy as np
import psygnal
import pymmcore
import pytest
from pymmcore import CMMCore, PropertySetting
from useq import MDASequence

from pymmcore_plus import (
    CMMCorePlus,
    Configuration,
    DeviceDetectionStatus,
    DeviceType,
    Metadata,
    PropertyType,
)


@pytest.fixture
def core():
    core = CMMCorePlus()
    if not core.getDeviceAdapterSearchPaths():
        pytest.fail(
            "To run tests, please install MM with `python -m pymmcore_plus.install`"
        )
    core.loadSystemConfiguration("demo")
    return core


def test_core(core: CMMCorePlus):
    assert isinstance(core, CMMCorePlus)
    assert isinstance(core, CMMCore)
    # because the fixture tries to find micromanager, this should be populated
    assert core.getDeviceAdapterSearchPaths()
    assert isinstance(core.events.propertyChanged, psygnal.SignalInstance)
    assert not core._canceled
    assert not core._paused

    # because the fixture loadsSystemConfig 'demo'
    assert len(core.getLoadedDevices()) == 12

    assert "CMMCorePlus" in repr(core)


def test_search_paths(core: CMMCorePlus):
    """Make sure search paths get added to path"""
    core.setDeviceAdapterSearchPaths(["test_path"])
    assert "test_path" in os.getenv("PATH")

    with pytest.raises(TypeError):
        core.setDeviceAdapterSearchPaths("test_path")


def test_cb_exceptions(core: CMMCorePlus, caplog):
    @core.events.propertyChanged.connect
    def _raze():
        raise ValueError("Boom")

    # using this to avoid our setProperty override... which would immediately
    # raise the exception (we want it to be raised deeper)
    pymmcore.CMMCore.setProperty(core, "Camera", "Binning", 2)

    msg = caplog.records[0].message
    assert msg == "Exception occured in MMCorePlus callback 'propertyChanged': Boom"


def test_new_position_methods(core: CMMCorePlus):
    x1, y1 = core.getXYPosition()
    z1 = core.getZPosition()

    core.setRelativeXYZPosition(1, 1, 1)

    x2, y2 = core.getXYPosition()
    z2 = core.getZPosition()

    assert round(x2, 2) == x1 + 1
    assert round(y2, 2) == y1 + 1
    assert round(z2, 2) == z1 + 1


def test_mda(core: CMMCorePlus):
    """Test signal emission during MDA"""
    mda = MDASequence(
        time_plan={"interval": 0.1, "loops": 2},
        stage_positions=[(1, 1, 1)],
        z_plan={"range": 3, "step": 1},
        channels=[{"config": "DAPI", "exposure": 1}],
    )
    fr_mock = MagicMock()
    ss_mock = MagicMock()
    sf_mock = MagicMock()
    xystage_mock = MagicMock()
    stage_mock = MagicMock()
    exp_mock = MagicMock()

    core.events.frameReady.connect(fr_mock)
    core.events.sequenceStarted.connect(ss_mock)
    core.events.sequenceFinished.connect(sf_mock)
    core.events.XYStagePositionChanged.connect(xystage_mock)
    core.events.stagePositionChanged.connect(stage_mock)
    core.events.exposureChanged.connect(exp_mock)

    core.run_mda(mda)
    assert fr_mock.call_count == len(list(mda))
    for event, _call in zip(mda, fr_mock.call_args_list):
        assert isinstance(_call.args[0], np.ndarray)
        assert _call.args[1] == event

    ss_mock.assert_called_once_with(mda)
    sf_mock.assert_called_once_with(mda)
    xystage_mock.assert_called_with("XY", 1.0, 1.0)
    exp_mock.assert_called_with("Camera", 1.0)
    stage_mock.assert_has_calls(
        [
            call("Z", -0.5),
            call("Z", 0.5),
            call("Z", 1.5),
            call("Z", 2.5),
            call("Z", -0.5),
            call("Z", 0.5),
            call("Z", 1.5),
            call("Z", 2.5),
        ]
    )


def test_mda_pause_cancel(core: CMMCorePlus):
    """Test signal emission during MDA with cancelation"""
    mda = MDASequence(
        time_plan={"interval": 0.1, "loops": 2},
        stage_positions=[(1, 1, 1)],
        z_plan={"range": 3, "step": 1},
        channels=[{"config": "DAPI", "exposure": 1}],
    )

    pause_mock = MagicMock()
    cancel_mock = MagicMock()
    sf_mock = MagicMock()
    ss_mock = MagicMock()

    core.events.sequenceStarted.connect(ss_mock)
    core.events.sequencePauseToggled.connect(pause_mock)
    core.events.sequenceCanceled.connect(cancel_mock)
    core.events.sequenceFinished.connect(sf_mock)

    _fcount = 0

    @core.events.frameReady.connect
    def _onframe(frame, event):
        nonlocal _fcount
        _fcount += 1
        if _fcount == 2:
            core.toggle_pause()
            pause_mock.assert_called_with(True)
            core.toggle_pause()
            pause_mock.assert_called_with(False)
        elif _fcount == 4:
            core.cancel()

    core.run_mda(mda)

    ss_mock.assert_called_once_with(mda)
    cancel_mock.assert_called_once_with(mda)
    assert _fcount == 4
    assert _fcount < len(list(mda))
    sf_mock.assert_called_once_with(mda)


def test_device_type_overrides(core: CMMCorePlus):
    dt = core.getDeviceType("Camera")
    assert isinstance(dt, DeviceType)
    assert str(dt) == "Camera"
    assert int(dt) == 2
    assert dt == DeviceType["Camera"]
    assert dt == DeviceType["CameraDevice"]
    assert dt == DeviceType(2)


def test_property_type_overrides(core: CMMCorePlus):
    pt = core.getPropertyType("Camera", "Binning")
    assert isinstance(pt, PropertyType)
    assert pt.to_python() is int


def test_detect_device(core: CMMCorePlus):
    dds = core.detectDevice("Camera")
    assert isinstance(dds, DeviceDetectionStatus)
    assert dds == -2 == DeviceDetectionStatus.Unimplemented


def test_metadata(core: CMMCorePlus):
    core.startContinuousSequenceAcquisition(10)
    core.stopSequenceAcquisition()
    image, md = core.getLastImageMD()
    assert isinstance(md, Metadata)
    assert md["Height"] == "512"
    assert "Binning" in md.keys()
    assert ("ImageNumber", "0") in md.items()
    assert "GRAY16" in md.values()

    assert "Camera" in md
    md["Camera"] = "new"
    assert md["Camera"] == "new" == md.get("Camera")

    cpy = md.copy()
    assert cpy == md

    del md["Camera"]
    assert "Camera" not in md

    assert "Camera" in cpy
    assert md.get("", 1) == 1  # default

    md.clear()
    assert not md

    assert isinstance(md.json(), str)


def test_new_metadata():
    md = Metadata({"a": "1"})
    assert md["a"] == "1"
    assert isinstance(md, pymmcore.Metadata)


def test_md_overrides(core: CMMCorePlus):
    core.startContinuousSequenceAcquisition(10)
    core.stopSequenceAcquisition()

    image, md = core.getNBeforeLastImageMD(0)
    assert isinstance(md, Metadata)

    image, md = core.popNextImageMD()
    assert isinstance(md, Metadata)


def test_configuration(core: CMMCorePlus):
    state = core.getSystemState()
    assert isinstance(state, Configuration)
    assert not isinstance(core.getSystemState(native=True), Configuration)

    assert str(state)

    tup = tuple(state)
    assert isinstance(tup, tuple)
    assert all(isinstance(x, tuple) and len(x) == 3 for x in tup)

    with pytest.raises(TypeError):
        assert state["Camera"] == 1
    with pytest.raises(TypeError):
        assert "Camera" in state

    assert state["Camera", "Binning"] == "1"
    assert PropertySetting("Camera", "Binning", "1") in state
    assert state in state

    assert ("Camera", "Binning") in state


def test_config_create():
    input = {"a": {"a0": "0", "a1": "1"}, "b": {"b0": "10", "b1": "11"}}
    aslist = [(d, p, v) for d, ps in input.items() for p, v in ps.items()]
    cfg1 = Configuration.create(input)
    cfg2 = Configuration.create(aslist)
    cfg3 = Configuration.create(a=input["a"], b=input["b"])
    assert cfg1.dict() == cfg2.dict() == cfg3.dict() == input
    assert list(cfg1) == list(cfg2) == list(cfg3) == aslist
    assert cfg1 == cfg2 == cfg3

    assert cfg1.json() == json.dumps(input)
    assert cfg1.html()


def test_config_yaml():
    input = {"a": {"a0": "0", "a1": "1"}, "b": {"b0": "10", "b1": "11"}}
    cfg1 = Configuration.create(input)
    yaml = pytest.importorskip("yaml")
    assert cfg1.yaml() == yaml.safe_dump(input)


def test_property_schema(core: CMMCorePlus):
    schema = core.getDeviceSchema("Camera")
    assert isinstance(schema, dict)
    assert schema["title"] == "DCam"
    assert schema["properties"]["AllowMultiROI"] == {"type": "boolean"}


def test_set_property_events(core: CMMCorePlus):
    """Test that using setProperty always emits a propertyChanged event."""
    mock = MagicMock()
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
