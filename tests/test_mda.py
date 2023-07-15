import time
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from useq import MDAEvent, MDASequence

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.events import MDASignaler

if TYPE_CHECKING:
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


def test_mda_failures(core: CMMCorePlus, qtbot: "QtBot"):
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


def test_autofocus(core: CMMCorePlus, qtbot: "QtBot", mock_fullfocus):
    # mock_autofocus sets z=100
    mda = MDASequence(
        stage_positions=[{"z": 50}],
        autofocus_plan={
            "autofocus_device_name": "Z",
            "autofocus_motor_offset": 50,
            "axes": ("p",),
        },
    )
    with qtbot.waitSignals(
        [
            core.mda.events.frameReady,
            core.mda.events.sequenceFinished,
        ]
    ):
        core.run_mda(mda)

    assert core.getPosition() == 100


def _assert_event_z_pos(core: CMMCorePlus, events: list[MDAEvent], expected: list):
    """Helper function to setup_event and assert expected z position"""
    for event, z in zip(events, expected):
        core.mda.engine.setup_event(event)
        core.mda.engine.exec_event(event)
        assert core.getPosition() == z


def test_autofocus_relative_z_plan_no_autofocus(
    core: CMMCorePlus, qtbot: "QtBot", mock_fullfocus
):
    # mock_autofocus sets z=100
    mda = MDASequence(
        stage_positions=[{"z": 50}],
        z_plan={"above": 1, "below": 1, "step": 1},
    )

    events = list(mda.iter_events())
    assert len(events) == 3

    assert events[0].z_pos == 49
    assert events[1].z_pos == 50
    assert events[2].z_pos == 51

    core.mda._engine.setup_event(events[0])
    assert core.getPosition() == 49.0

    _assert_event_z_pos(core, events, [49, 50, 51])


def test_autofocus_relative_z_plan(core: CMMCorePlus, qtbot: "QtBot", mock_fullfocus):
    # mock_autofocus sets z=100
    mda = MDASequence(
        stage_positions=[
            {
                "z": 25,
                "sequence": {
                    "autofocus_plan": {
                        "autofocus_device_name": "Z",
                        "autofocus_motor_offset": 50,
                        "axes": ("p",),
                    }
                },
            }
        ],
        z_plan={"above": 1, "below": 1, "step": 1},
    )

    events = list(mda.iter_events())

    assert len(events) == 4  # first event is the autofocus...

    assert events[0].z_pos == 25  # ...and should have the mid z stack position
    assert events[1].z_pos == 24
    assert events[2].z_pos == 25
    assert events[3].z_pos == 26

    _assert_event_z_pos(core, events, [100, 99, 100, 101])
    assert core.mda.engine._z_correction == {0: 75.0}
