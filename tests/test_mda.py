from __future__ import annotations

import time
from queue import Queue
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock, Mock, patch

import pytest
import useq
from useq import HardwareAutofocus, MDAEvent, MDASequence

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.events import MDASignaler

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from pytest import LogCaptureFixture
    from pytestqt.qtbot import QtBot

    from pymmcore_plus.mda import MDAEngine

try:
    import pytestqt
except ImportError:
    pytestqt = None

SKIP_NO_PYTESTQT = pytest.mark.skipif(
    pytestqt is None, reason="pytest-qt not installed"
)


def test_mda_waiting(core: CMMCorePlus) -> None:
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


def test_setting_position(core: CMMCorePlus) -> None:
    core.mda._running = True
    event1 = MDAEvent(
        exposure=123,
        x_pos=123,
        y_pos=456,
        z_pos=1,
        properties=[("Camera", "TestProperty1", 0.05)],
    )
    core.mda.engine.setup_event(event1)
    assert tuple(core.getXYPosition()) == (123, 456)
    assert core.getPosition() == 1
    assert core.getExposure() == 123
    assert core.getProperty("Camera", "TestProperty1") == "0.0500"

    # check that we aren't check things like: if event.x_pos
    # because then we will not set to zero
    event2 = MDAEvent(
        exposure=321,
        x_pos=0,
        y_pos=0,
        z_pos=0,
        properties=[("Camera", "TestProperty2", -0.07)],
    )
    core.mda.engine.setup_event(event2)
    assert tuple(core.getXYPosition()) == (0, 0)
    assert core.getPosition() == 0
    assert core.getExposure() == 321
    assert core.getProperty("Camera", "TestProperty2") == "-0.0700"


class BrokenEngine:
    def setup_sequence(self, sequence): ...

    def setup_event(self, event):
        raise ValueError("something broke")

    def exec_event(self, event): ...


@SKIP_NO_PYTESTQT
def test_mda_failures(core: CMMCorePlus, qtbot: QtBot) -> None:
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


# using a dict here instead of a useq.AxesBasedAF to force MDASequence to
# create a new instance.  This is because the AFPlan remembers the last axis
# it saw.  (it's kind of a bug that should be fixed in useq)
AFPlan = {"autofocus_device_name": "Z", "autofocus_motor_offset": 25, "axes": ("p",)}


@SKIP_NO_PYTESTQT
def test_autofocus(core: CMMCorePlus, qtbot: QtBot, mock_fullfocus) -> None:
    mda = MDASequence(stage_positions=[{"z": 0}], autofocus_plan=AFPlan)
    with qtbot.waitSignal(core.mda.events.sequenceFinished):
        core.mda.run(mda)

    engine = cast("MDAEngine", core.mda._engine)
    # the 50 here is because mock_full_focus shifts the z position by 50
    assert engine._z_correction[0] == 50


@SKIP_NO_PYTESTQT
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


@SKIP_NO_PYTESTQT
def test_autofocus_retries(core: CMMCorePlus, qtbot: QtBot, mock_fullfocus_failure):
    # mock_autofocus sets z=100
    # setting both z pos and autofocus offset to 25 because core does not have a
    # demo AF stage with both `State` and `Offset` properties.
    mda = MDASequence(
        stage_positions=[{"z": 25, "sequence": {"autofocus_plan": AFPlan}}],
        z_plan={"above": 1, "below": 1, "step": 1},
    )

    core.setZPosition(200)
    af_event = next(iter(mda.iter_events()))
    core.mda.engine.setup_event(af_event)
    core.mda.engine.exec_event(af_event)

    # if fullfocus fails, the returned z position should be the home position of the
    # z plan (50). If fullfocus is working, it should 100.
    assert core.getZPosition() == 25


@SKIP_NO_PYTESTQT
def test_set_mda_fov(core: CMMCorePlus, qtbot: QtBot):
    """Test that the fov size is updated."""
    mda = MDASequence(
        channels=["FITC"],
        stage_positions=({"sequence": {"grid_plan": {"rows": 1, "columns": 1}}},),
        grid_plan={"rows": 1, "columns": 1},
    )

    global_grid = mda.grid_plan
    sub_grid = mda.stage_positions[0].sequence.grid_plan  # type: ignore
    assert global_grid and sub_grid

    assert global_grid.fov_width == global_grid.fov_height is None
    assert sub_grid.fov_width == sub_grid.fov_height is None

    core.setProperty("Objective", "Label", "Nikon 20X Plan Fluor ELWD")
    core.mda.engine.setup_sequence(mda)  # type: ignore

    assert global_grid.fov_width == global_grid.fov_height == 256
    assert sub_grid.fov_width == sub_grid.fov_height == 256


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


@SKIP_NO_PYTESTQT
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


DEVICE_ERRORS: dict[str, list[str]] = {
    "XY": ["No XY stage device found. Cannot set XY position"],
    "Z": ["No Z stage device found. Cannot set Z position"],
    "Autofocus": ["No autofocus device found. Cannot execute autofocus"],
    "Camera": [
        "Failed to set exposure.",
        "Camera not loaded or initialized",
    ],
    "Dichroic": ['No device with label "Dichroic"'],
}


@pytest.mark.parametrize("device", DEVICE_ERRORS)
def test_mda_no_device(
    device: str, core: CMMCorePlus, caplog: LogCaptureFixture
) -> None:
    from pymmcore_plus._logger import logger

    logger.setLevel("DEBUG")
    try:
        core.unloadDevice(device)

        if device == "Autofocus":
            event = MDAEvent(
                action=HardwareAutofocus(
                    autofocus_device_name="Z", autofocus_motor_offset=10
                )
            )
        else:
            event = MDAEvent(x_pos=1, z_pos=1, exposure=1, channel={"config": "FITC"})
        engine = cast("MDAEngine", core.mda.engine)
        engine.setup_event(event)
        list(engine.exec_event(event))

        for e in DEVICE_ERRORS[device]:
            assert e in caplog.text
    finally:
        logger.setLevel("CRITICAL")


def test_keep_shutter_open(core: CMMCorePlus) -> None:
    # a 2-position sequence, where one position has a little time burst
    # and the other doesn't.  There is a z plan but we're only keeing shutter across
    # time.  The reason we use z is to do a little burst at each z, at one position
    # but not the other one (because only one position has time_plan)
    mda = MDASequence(
        axis_order="zpt",
        stage_positions=[
            (0, 0),
            useq.Position(
                sequence=MDASequence(
                    time_plan=useq.TIntervalLoops(interval=0.1, loops=3)
                )
            ),
        ],
        z_plan=useq.ZRangeAround(range=2, step=1),
        keep_shutter_open_across="t",
    )

    @core.mda.events.frameReady.connect
    def _on_frame(img: Any, event: MDAEvent) -> None:
        assert core.getShutterOpen() == event.keep_shutter_open
        # autoshutter will always be on only at position 0 (no time plan)
        assert core.getAutoShutter() == (event.index["p"] == 0)

    core.setAutoShutter(True)
    core.mda.run(mda)

    # It should look like this:
    # event,                                                   open, auto_shut
    # index={'p': 0, 'z': 0},                                  False, True)
    # index={'p': 1, 'z': 0, 't': 0}, keep_shutter_open=True), True, False)
    # index={'p': 1, 'z': 0, 't': 1}, keep_shutter_open=True), True, False)
    # index={'p': 1, 'z': 0, 't': 2},                          False, False)
    # index={'p': 0, 'z': 1},                                  False, True)
    # index={'p': 1, 'z': 1, 't': 0}, keep_shutter_open=True), True, False)
    # index={'p': 1, 'z': 1, 't': 1}, keep_shutter_open=True), True, False)
    # index={'p': 1, 'z': 1, 't': 2},                          False, False)
    # index={'p': 0, 'z': 2},                                  False, True)
    # index={'p': 1, 'z': 2, 't': 0}, keep_shutter_open=True), True, False)
    # index={'p': 1, 'z': 2, 't': 1}, keep_shutter_open=True), True, False)
    # index={'p': 1, 'z': 2, 't': 2},                          False, False)
    # index={'p': 0, 'z': 3},                                  False, True)
    # index={'p': 1, 'z': 3, 't': 0}, keep_shutter_open=True), True, False)
    # index={'p': 1, 'z': 3, 't': 1}, keep_shutter_open=True), True, False)
    # index={'p': 1, 'z': 3, 't': 2},                          False, False)


def test_engine_protocol(core: CMMCorePlus) -> None:
    mock1 = Mock()
    mock2 = Mock()
    mock3 = Mock()
    mock4 = Mock()
    mock5 = Mock()
    mock6 = Mock()

    class MyEngine:
        def setup_sequence(self, mda: MDASequence) -> None:
            mock1(mda)

        def setup_event(self, event: MDAEvent) -> None:
            mock2(event)

        def exec_event(self, event: MDAEvent) -> None:
            mock3(event)

        def teardown_event(self, event: MDAEvent) -> None:
            mock4(event)

        def teardown_sequence(self, mda: MDASequence) -> None:
            mock5(mda)

        def event_iterator(self, events: Iterable[MDAEvent]) -> Iterator[MDAEvent]:
            mock6(events)
            return iter(events)

    core.mda.set_engine(MyEngine())

    event = MDAEvent()
    core.mda.run([event])

    mock1.assert_called_once()
    mock2.assert_called_once_with(event)
    mock3.assert_called_once_with(event)
    mock4.assert_called_once_with(event)
    mock5.assert_called_once()
    mock6.assert_called_once_with([event])

    with pytest.raises(TypeError, match="does not conform"):
        core.mda.set_engine(object())  # type: ignore


@SKIP_NO_PYTESTQT
def test_runner_cancel(qtbot: QtBot) -> None:
    # not using the parametrized fixture because we only want to test Qt here.
    # see https://github.com/pymmcore-plus/pymmcore-plus/issues/95 and
    # https://github.com/pymmcore-plus/pymmcore-plus/pull/98
    # for what we're trying to avoid
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    core.mda.engine.use_hardware_sequencing = False

    engine = MagicMock(wraps=core.mda.engine)
    core.mda.set_engine(engine)
    event1 = MDAEvent()
    core.run_mda([event1, MDAEvent(min_start_time=10)])
    with qtbot.waitSignal(core.mda.events.sequenceCanceled):
        time.sleep(0.1)
        core.mda.cancel()

    engine.setup_sequence.assert_called_once()
    engine.setup_event.assert_called_once_with(event1)  # not twice


@SKIP_NO_PYTESTQT
def test_runner_pause(qtbot: QtBot) -> None:
    # not using the parametrized fixture because we only want to test Qt here.
    # see https://github.com/pymmcore-plus/pymmcore-plus/issues/95 and
    # https://github.com/pymmcore-plus/pymmcore-plus/pull/98
    # for what we're trying to avoid
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    core.mda.engine.use_hardware_sequencing = False

    engine = MagicMock(wraps=core.mda.engine)
    core.mda.set_engine(engine)
    with qtbot.waitSignal(core.mda.events.frameReady):
        thread = core.run_mda([MDAEvent(), MDAEvent(min_start_time=2)])
    engine.setup_event.assert_called_once()  # not twice

    with qtbot.waitSignal(core.mda.events.sequencePauseToggled):
        core.mda.toggle_pause()
    time.sleep(1)
    with qtbot.waitSignal(core.mda.events.sequencePauseToggled):
        core.mda.toggle_pause()

    assert core.mda._paused_time > 0

    with qtbot.waitSignal(core.mda.events.sequenceFinished):
        thread.join()
    assert engine.setup_event.call_count == 2
    engine.teardown_sequence.assert_called_once()


def test_reset_event_timer(core: CMMCorePlus) -> None:
    seq = [
        MDAEvent(min_start_time=0),
        MDAEvent(min_start_time=0.2),
        MDAEvent(min_start_time=0, reset_event_timer=True),
        MDAEvent(min_start_time=0.2),
    ]
    meta: list[float] = []
    core.mda.events.frameReady.connect(lambda f, e, m: meta.append(m["runner_time_ms"]))
    core.mda.run(seq)
    # ensure that the 4th event occurred at least 190ms after the 3rd event
    # (allow some jitter)
    assert meta[3] >= meta[2] + 190


def test_queue_mda(core: CMMCorePlus) -> None:
    """Test running a Queue iterable"""
    mock_engine = MagicMock(wraps=core.mda.engine)
    core.mda.set_engine(mock_engine)

    queue: Queue[MDAEvent | None] = Queue()
    queue.put(MDAEvent(index={"t": 0}))
    queue.put(MDAEvent(index={"t": 1}))
    queue.put(None)
    iterable_queue = iter(queue.get, None)

    core.mda.run(iterable_queue)
    # make sure that the engine's iterator was NOT used when running an iter(Queue)
    mock_engine.event_iterator.assert_not_called()
    assert mock_engine.setup_event.call_count == 2


def test_get_handlers(core: CMMCorePlus) -> None:
    """Test that we can get the handlers"""
    runner = core.mda

    assert not runner.get_output_handlers()
    on_start_names: list[str] = []
    on_finish_names: list[str] = []

    @runner.events.sequenceStarted.connect
    def _on_start() -> None:
        on_start_names.extend([type(h).__name__ for h in runner.get_output_handlers()])

    @runner.events.sequenceFinished.connect
    def _on_end() -> None:
        on_finish_names.extend([type(h).__name__ for h in runner.get_output_handlers()])

    runner.run([MDAEvent()], output="memory://")

    # weakref is used to store the handlers,
    # handlers should be cleared after the sequence is finished
    assert not runner.get_output_handlers()
    # but they should have been available during start and finish events
    assert on_start_names == ["TensorStoreHandler"]
    assert on_finish_names == ["TensorStoreHandler"]


def test_custom_action(core: CMMCorePlus) -> None:
    """Make sure we can handle custom actions gracefully"""

    core.mda.run([MDAEvent(action=useq.CustomAction())])
