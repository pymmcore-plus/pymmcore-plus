from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Iterable, Iterator, cast
from unittest.mock import MagicMock, Mock, patch

import pytest
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.events import MDASignaler
from useq import AxesBasedAF, MDAEvent, MDASequence

if TYPE_CHECKING:
    from pymmcore_plus.mda import MDAEngine
    from pytestqt.qtbot import QtBot


def test_mda_waiting(core: CMMCorePlus):
    seq = MDASequence(
        channels=["Cy5"],
        time_plan={"interval": 1.5, "loops": 2},
        axis_order="tpcz",
        stage_positions=[(222, 1, 1), (111, 0, 0)],
    )
    t0 = time.perf_counter()
    core.run_mda(seq).join()
    t1 = time.perf_counter()

    # check that we actually waited
    # could expand to check that the actual times between events is correct
    # but this would catch a breakdown of not waiting at all
    assert t1 - t0 >= 1.5


def test_setting_position(core: CMMCorePlus):
    core.mda._running = True
    event1 = MDAEvent(exposure=123, x_pos=123, y_pos=456, z_pos=1)
    core.mda.engine.setup_event(event1)
    assert tuple(core.getXYPosition()) == (123, 456)
    assert core.getPosition() == 1
    assert core.getExposure() == 123

    # check that we aren't check things like: if event.x_pos
    # because then we will not set to zero
    event2 = MDAEvent(exposure=321, x_pos=0, y_pos=0, z_pos=0)
    core.mda.engine.setup_event(event2)
    assert tuple(core.getXYPosition()) == (0, 0)
    assert core.getPosition() == 0
    assert core.getExposure() == 321


class BrokenEngine:
    def setup_sequence(self, sequence):
        ...

    def setup_event(self, event):
        raise ValueError("something broke")

    def exec_event(self, event):
        ...


def test_mda_failures(core: CMMCorePlus, qtbot: QtBot):
    mda = MDASequence(
        channels=["Cy5"],
        time_plan={"interval": 1.5, "loops": 2},
        axis_order="tpcz",
        stage_positions=[(222, 1, 1), (111, 0, 0)],
    )

    # error in user callback
    def cb(img, event):
        raise ValueError("uh oh")

    core.mda.events.frameReady.connect(cb)

    if isinstance(core.mda.events, MDASignaler):
        with qtbot.waitSignal(core.mda.events.sequenceFinished):
            core.mda.run(mda)

    assert not core.mda.is_running()
    assert not core.mda.is_paused()
    assert not core.mda._canceled
    core.mda.events.frameReady.disconnect(cb)

    # Hardware failure
    # e.g. a serial connection error
    # we should fail gracefully
    with patch.object(core.mda, "_engine", BrokenEngine()):
        if isinstance(core.mda.events, MDASignaler):
            with qtbot.waitSignal(core.mda.events.sequenceFinished):
                with pytest.raises(ValueError):
                    core.mda.run(mda)
        else:
            with qtbot.waitSignal(core.mda.events.sequenceFinished):
                with pytest.raises(ValueError):
                    core.mda.run(mda)
        assert not core.mda.is_running()
        assert not core.mda.is_paused()
        assert not core.mda._canceled


AFPlan = AxesBasedAF(autofocus_device_name="Z", autofocus_motor_offset=25, axes=("p",))


def test_autofocus(core: CMMCorePlus, qtbot: QtBot, mock_fullfocus):
    mda = MDASequence(stage_positions=[{"z": 50}], autofocus_plan=AFPlan)
    with qtbot.waitSignal(core.mda.events.sequenceFinished):
        core.run_mda(mda)

    engine = cast("MDAEngine", core.mda._engine)
    # the 50 here is because mock_full_focus shifts the z position by 50
    assert engine._z_correction[0] == 50


def test_autofocus_relative_z_plan(
    core: CMMCorePlus, qtbot: QtBot, mock_fullfocus: Any
) -> None:
    # setting both z pos and autofocus offset to 25 because core does not have a
    # demo AF stage with both `State` and `Offset` properties.
    mda = MDASequence(
        stage_positions=[{"z": 25, "sequence": {"autofocus_plan": AFPlan}}],
        z_plan={"above": 1, "below": 1, "step": 1},
    )

    z_positions = []  # will be populated by _snap

    def _snap(*args):
        z_positions.append(core.getZPosition())
        core.snapImage(*args)

    # mock the engine core snap to store the z position
    mock_core = MagicMock(wraps=core)
    mock_core.snapImage.side_effect = _snap
    core.mda.engine._mmc = mock_core
    core.mda.run(mda)

    # the mock_fullfocus fixture nudges the focus upward by 50
    # so we should have ranged around z of 25 + 50 = 75
    assert z_positions == [74, 75, 76]
    assert core.mda.engine._z_correction == {0: 50.0}  # saved the correction


def test_autofocus_retries(core: CMMCorePlus, qtbot: QtBot, mock_fullfocus_failure):
    # mock_autofocus sets z=100
    # setting both z pos and autofocus offset to 25 because core does not have a
    # demo AF stage with both `State` and `Offset` properties.
    mda = MDASequence(
        stage_positions=[{"z": 25, "sequence": {"autofocus_plan": AFPlan}}],
        z_plan={"above": 1, "below": 1, "step": 1},
    )

    core.setZPosition(200)
    af_event = list(mda.iter_events())[0]
    core.mda.engine.setup_event(af_event)
    core.mda.engine.exec_event(af_event)

    # if fullfocus fails, the returned z position should be the home position of the
    # z plan (50). If fullfocus is working, it should 100.
    assert core.getZPosition() == 25


def test_set_mda_fov(core: CMMCorePlus, qtbot: QtBot):
    """Test that the fov size is updated."""
    mda = MDASequence(
        channels=[
            {"config": "FITC", "exposure": 3},
        ],
        stage_positions=(
            {"sequence": {"grid_plan": {"rows": 2, "columns": 1}}},
            {"sequence": {"grid_plan": {"rows": 1, "columns": 1}}},
        ),
    )

    core.setProperty("Objective", "Label", "Nikon 20X Plan Fluor ELWD")

    assert mda._fov_size == (1, 1)
    assert mda.stage_positions[0].sequence._fov_size == (1, 1)
    assert mda.stage_positions[1].sequence._fov_size == (1, 1)

    core.mda.engine.setup_sequence(mda)

    assert mda._fov_size == (256, 256)
    assert mda.stage_positions[0].sequence._fov_size == (256, 256)
    assert mda.stage_positions[1].sequence._fov_size == (256, 256)


def event_generator() -> Iterator[MDAEvent]:
    yield MDAEvent()
    yield MDAEvent()
    return


SEQS = [
    MDASequence(time_plan={"interval": 0.1, "loops": 2}),
    (MDAEvent(), MDAEvent()),
    # the core fixture runs twice ... so we need to make this generator each time
    "event_generator()",
]


@pytest.mark.parametrize("seq", SEQS)
def test_mda_iterable_of_events(
    core: CMMCorePlus, seq: Iterable[MDAEvent], qtbot: QtBot
) -> None:
    if seq == "event_generator()":  # type: ignore
        seq = event_generator()
    start_mock = Mock()
    frame_mock = Mock()
    core.mda.events.sequenceStarted.connect(start_mock)
    core.mda.events.frameReady.connect(frame_mock)

    with qtbot.waitSignal(core.mda.events.sequenceFinished):
        core.mda.run(seq)

    assert start_mock.call_count == 1
    assert frame_mock.call_count == 2
