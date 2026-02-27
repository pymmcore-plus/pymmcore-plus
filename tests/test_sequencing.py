import os
import platform
from collections.abc import Iterator
from contextlib import suppress
from math import prod
from typing import cast
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest
import useq

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.core._sequencing import (
    SequencedEvent,
    get_all_sequenceable,
    iter_sequenced_events,
)
from pymmcore_plus.mda import MDAEngine, MDARunner
from pymmcore_plus.mocks import MockSequenceableCore
from pymmcore_plus.seq_tester import decode_image

with suppress(ImportError):
    pass


def test_get_all_sequencable(core: CMMCorePlus) -> None:
    d = get_all_sequenceable(core)
    assert d[("Objective", "State")] == 10


def test_sequenced_mda(core: CMMCorePlus) -> None:
    NLOOPS = 8
    mda = useq.MDASequence(
        axis_order="pct",  # do complete t for each c at each p
        stage_positions=[(0, 0), (1, 1)],
        channels=[
            useq.Channel(config="DAPI", exposure=5),
            useq.Channel(config="FITC", exposure=10),
        ],
        time_plan=useq.TIntervalLoops(interval=0, loops=NLOOPS),
    )
    EXPECTED_SEQUENCES = 4  # timeseries at each of 2 positions, 2 channels

    core_mock = cast("CMMCorePlus", MagicMock(wraps=core))  # so we can spy on all_calls
    engine = MDAEngine(mmc=core_mock, restore_initial_state=False)

    engine.use_hardware_sequencing = False
    engine.force_set_xy_position = False
    assert len(list(engine.event_iterator(mda))) == NLOOPS * 2 * 2

    engine.use_hardware_sequencing = True
    events = list(engine.event_iterator(mda))
    assert len(events) == EXPECTED_SEQUENCES

    engine.use_hardware_sequencing = True

    runner = MDARunner()
    runner.set_engine(engine)

    core_mock.startSequenceAcquisition.assert_not_called()

    runner.run(mda)
    assert core_mock.startSequenceAcquisition.call_count == EXPECTED_SEQUENCES
    core_mock.startSequenceAcquisition.assert_called_with(NLOOPS, 0, True)

    expected_ch = [call("Channel", "DAPI"), call("Channel", "FITC")] * 2
    assert core_mock.setConfig.call_args_list == expected_ch

    expected_exposure = [call(5), call(10)] * 2
    assert core_mock.setExposure.call_args_list == expected_exposure

    expected_pos = [call(0, 0), call(1, 1)]
    assert core_mock.setXYPosition.call_args_list == expected_pos


def test_sequenced_mda_with_zero_values() -> None:
    # just testing a bug I found where if z, x, or y are 0, they accidentally
    # get sequenced
    mda = useq.MDASequence(z_plan=useq.ZRangeAround(range=3.0, step=0.5))
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    core.mda.engine.use_hardware_sequencing = True
    core.mda.run(mda)


def test_fully_sequenceable_core(core: CMMCorePlus) -> None:
    mda = useq.MDASequence(
        stage_positions=[(0, 0, 0), (1, 1, 1)],
        z_plan=useq.ZRangeAround(range=3, step=1),
        channels=[
            useq.Channel(config="DAPI", exposure=5),
            useq.Channel(config="FITC", exposure=10),
        ],
        time_plan=useq.TIntervalLoops(interval=0, loops=3),
    )

    core_mock = MockSequenceableCore(wraps=core)

    engine = MDAEngine(mmc=core_mock, use_hardware_sequencing=True)

    combined_events = list(iter_sequenced_events(core_mock, mda))
    assert len(combined_events) == 1
    seq_event = combined_events[0]
    assert isinstance(seq_event, SequencedEvent)

    runner = MDARunner()
    runner.set_engine(engine)
    runner.run(mda)

    n_img = prod(mda.shape)
    core_mock.startSequenceAcquisition.assert_called_once_with(n_img, 0, True)
    core_mock.loadExposureSequence.assert_called()


def test_sequenced_event_teardown(core: CMMCorePlus) -> None:
    """Assert teardown_event receives the SequencedEvent, not inner events."""
    mda = useq.MDASequence(
        z_plan=useq.ZRangeAround(range=2, step=1),
        time_plan=useq.TIntervalLoops(interval=0, loops=3),
    )

    core_mock = MockSequenceableCore(wraps=core)
    engine = MDAEngine(mmc=core_mock, use_hardware_sequencing=True)
    runner = MDARunner()
    runner.set_engine(engine)
    with patch.object(engine, "teardown_event") as mock_teardown:
        runner.run(mda)

    teardown_calls = [call.args[0] for call in mock_teardown.call_args_list]
    assert len(teardown_calls) == 1
    assert isinstance(teardown_calls[0], SequencedEvent)


def test_sequenced_circular_buffer(core: CMMCorePlus) -> None:
    core.initializeCircularBuffer()
    core.setCircularBufferMemoryFootprint(20)
    max_imgs = core.getBufferFreeCapacity()
    mda = useq.MDASequence(
        channels=["DAPI"],
        time_plan=useq.TIntervalLoops(interval=0, loops=max_imgs * 2),
    )
    core.mda.engine.use_hardware_sequencing = True
    core.mda.run(mda)


@pytest.fixture
def sequence_tester() -> Iterator[CMMCorePlus]:
    core = CMMCorePlus()
    try:
        core.loadDevice("THub", "SequenceTester", "THub")
    except RuntimeError:
        pytest.xfail("Cannot load SequenceTester library")

    core.initializeDevice("THub")
    core.loadDevice("TCamera", "SequenceTester", "TCamera")
    core.setParentLabel("TCamera", "THub")
    core.setProperty("TCamera", "ImageMode", "MachineReadable")
    core.setProperty("TCamera", "ImageWidth", 128)
    core.setProperty("TCamera", "ImageHeight", 128)
    core.initializeDevice("TCamera")
    core.setCameraDevice("TCamera")
    yield core


@pytest.mark.skipif(
    bool(os.getenv("CI") and platform.machine() == "arm64"),
    reason="macos-latest having issues with SequenceTester on CI",
)
def test_sequence_tester_decoding(sequence_tester: CMMCorePlus) -> None:
    core = sequence_tester
    core.startContinuousSequenceAcquisition(3)
    core.waitForSystem()
    core.stopSequenceAcquisition()

    for i in range(3):
        info = decode_image(core.popNextImage())
        assert info.camera_info.is_sequence

        assert info.hub_global_packet_nr == i
        assert info.camera_info.cumulative_img_num == i
        assert info.camera_info.frame_num == i
        assert info.camera_info.serial_img_num == i

        assert bool(info.start_state) == (i != 0)


def test_sequence_actions(core: CMMCorePlus) -> None:
    mda = useq.MDASequence(
        axis_order="ptc",  # do complete t for each c at each p
        stage_positions=[(0, 0), (1, 1)],
        channels=[useq.Channel(config="FITC", exposure=10)],
        time_plan=useq.TIntervalLoops(interval=0, loops=5),
        autofocus_plan={"autofocus_motor_offset": 25, "axes": ("p",)},
    )
    EXPECTED_SEQUENCES = 4  # 2 autofocus actions and 2 timeseries

    core_mock = cast("CMMCorePlus", MagicMock(wraps=core))
    engine = MDAEngine(mmc=core_mock)
    engine.use_hardware_sequencing = True
    events = list(engine.event_iterator(mda))
    assert len(events) == EXPECTED_SEQUENCES


@pytest.mark.parametrize("interval", [0, 1])
def test_sequencing_respects_min_interval(core: CMMCorePlus, interval: float) -> None:
    # Create sequence and generate events
    seq = useq.MDASequence(
        z_plan={"range": 1.0, "step": 1.0},
        time_plan={"interval": interval, "loops": 3},
    )

    core.setExposure(1)
    core.setProperty("Z", "UseSequences", "Yes")
    core.mda.engine.use_hardware_sequencing = True
    merged = list(iter_sequenced_events(core, seq))
    assert len(list(seq)) == 6
    assert len(merged) == 1 if interval == 0 else 3
    expected_interval = [0, 1 * interval, 2 * interval] if interval else [0]
    assert [e.min_start_time for e in merged] == expected_interval


@pytest.fixture
def multicam_tester() -> Iterator[CMMCorePlus]:
    """Multi-camera SequenceTester fixture."""
    core = CMMCorePlus()
    core.loadDevice("THub", "SequenceTester", "THub")

    core.initializeDevice("THub")

    # Load two test cameras (each with unique adapter name)
    for cam_name, adapter_name in [("TCam1", "TCamera1"), ("TCam2", "TCamera2")]:
        core.loadDevice(cam_name, "SequenceTester", adapter_name)
        core.setParentLabel(cam_name, "THub")
        core.setProperty(cam_name, "ImageMode", "MachineReadable")
        core.setProperty(cam_name, "ImageWidth", 128)
        core.setProperty(cam_name, "ImageHeight", 128)
        core.initializeDevice(cam_name)

    # Create Multi Camera and assign physical cameras
    core.loadDevice("MCam", "Utilities", "Multi Camera")
    core.initializeDevice("MCam")
    core.setProperty("MCam", "Physical Camera 1", "TCam1")
    core.setProperty("MCam", "Physical Camera 2", "TCam2")
    core.setCameraDevice("MCam")

    yield core


def test_sequenced_multicam_events(multicam_tester: CMMCorePlus) -> None:
    """Verify multi-camera frames are emitted in sequential (t,c) order.

    Even though cameras produce frames asynchronously, the engine should buffer
    and emit them in predictable order: (t=0,c=0), (t=0,c=1), (t=1,c=0), (t=1,c=1)...
    """
    core = multicam_tester
    frames: list[tuple[int, int, str]] = []  # (timepoint, channel, camera_name)

    @core.mda.events.frameReady.connect
    def on_frame(img: np.ndarray, event: useq.MDAEvent) -> None:
        info = decode_image(img)
        frames.append((event.index["t"], event.index["cam"], info.camera_info.name))

    core.mda.run(useq.MDASequence(time_plan={"interval": 0, "loops": 5}))

    # Verify we got all frames (5 timepoints x 2 cameras = 10 frames)
    assert len(frames) == 10

    # Verify frames arrive in perfect sequential order
    expected = [(t, c, f"TCamera{c + 1}") for t in range(5) for c in range(2)]
    assert frames == expected
