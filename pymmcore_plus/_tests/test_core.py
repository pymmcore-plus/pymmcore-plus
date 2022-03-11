import json
import os
import re
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, call, patch

import numpy as np
import psygnal
import pymmcore
import pytest
from pymmcore import CMMCore, PropertySetting
from qtpy.QtCore import QObject
from qtpy.QtCore import SignalInstance as QSignalInstance
from useq import MDASequence

from pymmcore_plus import (
    CMMCorePlus,
    Configuration,
    DeviceDetectionStatus,
    DeviceType,
    Metadata,
    PropertyType,
)
from pymmcore_plus.core.events import CMMCoreSignaler
from pymmcore_plus.mda import MDAEngine

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def test_core(core: CMMCorePlus):
    assert isinstance(core, CMMCorePlus)
    assert isinstance(core, CMMCore)
    # because the fixture tries to find micromanager, this should be populated
    assert core.getDeviceAdapterSearchPaths()
    assert isinstance(
        core.events.propertyChanged, (psygnal.SignalInstance, QSignalInstance)
    )
    assert isinstance(
        core.mda.events.frameReady, (psygnal.SignalInstance, QSignalInstance)
    )
    assert not core.mda._canceled
    assert not core.mda._paused

    # because the fixture loadsSystemConfig 'demo'
    assert len(core.getLoadedDevices()) == 12

    assert "CMMCorePlus" in repr(core)


def test_search_paths(core: CMMCorePlus):
    """Make sure search paths get added to path"""
    core.setDeviceAdapterSearchPaths(["test_path"])
    assert "test_path" in os.getenv("PATH")

    with pytest.raises(TypeError):
        core.setDeviceAdapterSearchPaths("test_path")


def test_load_system_config(core: CMMCorePlus):
    with pytest.raises(FileNotFoundError):
        core.loadSystemConfiguration("nonexistent")

    config_path = Path(__file__).parent / "local_config.cfg"
    core.loadSystemConfiguration(str(config_path))
    assert core.getLoadedDevices() == (
        "DHub",
        "Camera",
        "Dichroic",
        "Emission",
        "Excitation",
        "Objective",
        "Z",
        "Path",
        "XY",
        "Shutter",
        "Autofocus",
        "Core",
    )


def test_cb_exceptions(core: CMMCorePlus, caplog, qtbot: "QtBot"):
    @core.events.propertyChanged.connect
    def _raze():
        raise ValueError("Boom")

    # using this to avoid our setProperty override... which would immediately
    # raise the exception (we want it to be raised deeper)
    if isinstance(core.events, CMMCoreSignaler):
        pymmcore.CMMCore.setProperty(core, "Camera", "Binning", 2)
        msg = caplog.records[0].message
        assert msg == "Exception occured in MMCorePlus callback 'propertyChanged': Boom"
    else:
        with qtbot.capture_exceptions() as exceptions:
            with qtbot.waitSignal(core.events.propertyChanged):
                pymmcore.CMMCore.setProperty(core, "Camera", "Binning", 2)
        assert len(exceptions) == 1
        assert str(exceptions[0][1]) == "Boom"


def test_new_position_methods(core: CMMCorePlus):
    x1, y1 = core.getXYPosition()
    z1 = core.getZPosition()

    core.setRelativeXYZPosition(1, 1, 1)

    x2, y2 = core.getXYPosition()
    z2 = core.getZPosition()

    assert round(x2, 2) == x1 + 1
    assert round(y2, 2) == y1 + 1
    assert round(z2, 2) == z1 + 1


def test_mda(core: CMMCorePlus, qtbot: "QtBot"):
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

    core.mda._events.frameReady.connect(fr_mock)
    core.mda._events.sequenceStarted.connect(ss_mock)
    core.mda._events.sequenceFinished.connect(sf_mock)
    core.events.XYStagePositionChanged.connect(xystage_mock)
    core.events.stagePositionChanged.connect(stage_mock)
    core.events.exposureChanged.connect(exp_mock)

    with qtbot.waitSignal(core.mda._events.sequenceFinished):
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


def test_mda_pause_cancel(core: CMMCorePlus, qtbot: "QtBot"):
    """Test signal emission during MDA with cancelation"""
    mda = MDASequence(
        time_plan={"interval": 0.25, "loops": 10},
        stage_positions=[(1, 1, 1)],
        z_plan={"range": 3, "step": 1},
        channels=[{"config": "DAPI", "exposure": 1}],
    )

    pause_mock = MagicMock()
    cancel_mock = MagicMock()
    sf_mock = MagicMock()
    ss_mock = MagicMock()

    core.mda._events.sequenceStarted.connect(ss_mock)
    core.mda._events.sequencePauseToggled.connect(pause_mock)
    core.mda._events.sequenceCanceled.connect(cancel_mock)
    core.mda._events.sequenceFinished.connect(sf_mock)

    _fcount = 0

    @core.mda._events.frameReady.connect
    def _onframe(frame, event):
        nonlocal _fcount
        _fcount += 1
        if _fcount == 1:
            core.mda.toggle_pause()
            pause_mock.assert_called_with(True)
            core.mda.toggle_pause()
            pause_mock.assert_called_with(False)
        elif _fcount == 2:
            core.mda.cancel()

    with qtbot.waitSignal(core.mda._events.sequenceFinished):
        core.run_mda(mda)

    ss_mock.assert_called_once_with(mda)
    cancel_mock.assert_called_once_with(mda)
    assert _fcount < len(list(mda))
    sf_mock.assert_called_once_with(mda)


def test_register_mda_engine(core: CMMCorePlus, qtbot: "QtBot"):
    orig_engine = core.mda

    registered_mock = MagicMock()
    core.events.mdaEngineRegistered.connect(registered_mock)

    # fake that mda is running
    # with an actual mda the threading and timing is
    # such that this ends up being a flaky test if we
    # use `core.run_mda`
    core.mda._running = True
    new_engine = MDAEngine(core)
    with pytest.raises(ValueError):
        core.register_mda_engine(new_engine)
    core.mda._running = False

    with qtbot.waitSignal(core.events.mdaEngineRegistered):
        core.register_mda_engine(new_engine)
    assert core._mda_engine is new_engine

    # invalid engine
    class nonconforming_engine:
        pass

    with pytest.raises(TypeError):
        core.register_mda_engine(nonconforming_engine())
    registered_mock.assert_called_once_with(new_engine, orig_engine)


def test_not_concurrent_mdas(core, qtbot: "QtBot"):
    mda = MDASequence(
        time_plan={"interval": 0.1, "loops": 2},
        stage_positions=[(1, 1, 1)],
        z_plan={"range": 3, "step": 1},
        channels=[{"config": "DAPI", "exposure": 1}],
    )
    core.mda._running = True
    assert core.mda.is_running()
    with pytest.raises(ValueError):
        core.run_mda(mda)
    core.mda._running = False
    core.run_mda(mda)
    core.mda.cancel()


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
    assert "ImageNumber" in md.keys()
    assert ("Binning", "1") in md.items()
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


def test_get_objectives(core: CMMCorePlus):
    devices = core.guessObjectiveDevices()
    assert len(devices) == 1
    assert devices[0] == "Objective"

    with pytest.raises(TypeError):
        core.objective_device_pattern = 4

    # assign a new regex that won't match Objective using a str
    core.objective_device_pattern = "^((?!Objective).)*$"
    assert "Objective" not in core.guessObjectiveDevices()

    # assign new using a pre-compile pattern
    core.objective_device_pattern = re.compile("Objective")
    devices = core.guessObjectiveDevices()
    assert len(devices) == 1
    assert devices[0] == "Objective"


def test_guess_channel_group(core: CMMCorePlus):

    chan_group = core.getChannelGroup()
    assert chan_group == "Channel"

    assert core.getOrGuessChannelGroup() == ["Channel"]

    with patch.object(core, "getChannelGroup", return_value=""):
        assert core.getOrGuessChannelGroup() == ["Channel"]

        with pytest.raises(TypeError):
            core.channelGroup_pattern = 4

        # assign a new regex that won't match Channel using a str
        # this will return all the mm groups, but that's because this a bad regex
        # to use
        core.channelGroup_pattern = "^((?!(Channel)).)*$"
        assert core.getOrGuessChannelGroup() == [
            "Camera",
            "LightPath",
            "Objective",
            "System",
        ]

        # assign new using a pre-compile pattern
        core.channelGroup_pattern = re.compile("Channel")
        chan_group = core.getOrGuessChannelGroup()
        assert chan_group == ["Channel"]


def test_lock_and_callbacks(core: CMMCorePlus, qtbot):
    if not isinstance(core.events, QObject):
        pytest.skip(reason="Skip lock tests on psygnal until we can remove qtbot.")

    # when a function with a lock triggers a callback
    # that callback should be able to call locked functions
    # without hanging.

    # do some threading silliness here so we don't accidentally hang our
    # test if things go wrong have to use *got_lock* to check because we
    # can't assert in the function as theads don't throw their exceptions
    # back into the calling thread.
    got_lock = False

    def cb(*args, **kwargs):
        nonlocal got_lock
        got_lock = core.lock.acquire(timeout=0.1)
        if got_lock:
            core.lock.release()

    core.events.XYStagePositionChanged.connect(cb)

    def trigger_cb():
        core.setXYPosition(4, 5)

    th = Thread(target=trigger_cb)
    with qtbot.waitSignal(core.events.XYStagePositionChanged):
        th.start()
    assert got_lock
    got_lock = False

    core.mda._events.frameReady.connect(cb)
    mda = MDASequence(
        time_plan={"interval": 0.1, "loops": 2},
        stage_positions=[(1, 1, 1)],
        z_plan={"range": 3, "step": 1},
        channels=[{"config": "DAPI", "exposure": 1}],
    )

    with qtbot.waitSignal(core.mda._events.sequenceFinished):
        core.run_mda(mda)
    assert got_lock


def test_single_instance():
    core1 = CMMCorePlus.instance()
    core2 = CMMCorePlus.instance()
    assert core1 is core2


def test_setPosition_overload(core: CMMCorePlus):
    core.setPosition(5)
    dev = core.getFocusDevice()
    core.setPosition(dev, 4)


def test_unload_devices(core: CMMCorePlus):
    assert len(core.getLoadedDevices()) > 2
    core.unloadAllDevices()
    assert len(core.getLoadedDevices()) == 1
