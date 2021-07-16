import os
from unittest.mock import MagicMock, call

import numpy as np
import psygnal
import pytest
from pymmcore import CMMCore
from useq import MDASequence

from pymmcore_plus import CMMCorePlus
from pymmcore_plus._util import find_micromanager


def _pymmcore():
    mmc = CMMCore()
    mmpath = find_micromanager()
    mmc.setDeviceAdapterSearchPaths([mmpath])
    mmc.loadSystemConfiguration(os.path.join(mmpath, "MMConfig_demo.cfg"))


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


def test_search_paths(core: CMMCorePlus):
    """Make sure search paths get added to path"""
    core.setDeviceAdapterSearchPaths(["test_path"])
    assert "test_path" in os.getenv("PATH")

    with pytest.raises(TypeError):
        core.setDeviceAdapterSearchPaths("test_path")


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
