from math import prod
from typing import cast
from unittest.mock import MagicMock, call

import pytest
import useq

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.core._sequencing import SequencedEvent, get_all_sequenceable
from pymmcore_plus.mda import MDAEngine, MDARunner
from pymmcore_plus.seq_tester import decode_image


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
    engine = MDAEngine(mmc=core_mock)

    engine.use_hardware_sequencing = False
    assert len(list(engine.event_iterator(mda))) == NLOOPS * 2 * 2

    engine.use_hardware_sequencing = True
    events = list(engine.event_iterator(mda))
    assert len(events) == EXPECTED_SEQUENCES

    engine.use_hardware_sequencing = True

    runner = MDARunner()
    runner.set_engine(engine)

    runner.run(mda)
    assert core_mock.prepareSequenceAcquisition.call_count == EXPECTED_SEQUENCES
    assert core_mock.startSequenceAcquisition.call_count == EXPECTED_SEQUENCES
    core_mock.startSequenceAcquisition.assert_called_with(NLOOPS, 0, True)

    expected_ch = [call("Channel", "DAPI"), call("Channel", "FITC")] * 2
    assert core_mock.setConfig.call_args_list == expected_ch

    expected_exposure = [call(5), call(10)] * 2
    assert core_mock.setExposure.call_args_list == expected_exposure

    expected_pos = [call(0, 0), call(0, 0), call(1, 1), call(1, 1)]
    assert core_mock.setXYPosition.call_args_list == expected_pos


def test_sequenced_mda_with_zero_values() -> None:
    # just testing a bug I found where if z, x, or y are 0, they accidentally
    # get sequenced
    mda = useq.MDASequence(z_plan=useq.ZRangeAround(range=3.0, step=0.5))
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    core.mda.engine.use_hardware_sequencing = True
    core.mda.run(mda)


def test_fully_sequenceable_core() -> None:
    mda = useq.MDASequence(
        stage_positions=[(0, 0, 0), (1, 1, 1)],
        z_plan=useq.ZRangeAround(range=3, step=1),
        channels=[
            useq.Channel(config="DAPI", exposure=5),
            useq.Channel(config="FITC", exposure=10),
        ],
        time_plan=useq.TIntervalLoops(interval=0, loops=3),
    )

    CAM = "Camera"
    XYSTAGE = "XYStage"
    FOCUS = "Z"
    core_mock = cast("CMMCorePlus", MagicMock(spec=CMMCorePlus))
    core_mock.isSequenceRunning.return_value = False
    core_mock.getRemainingImageCount.return_value = 0
    core_mock.isBufferOverflowed.return_value = False
    core_mock.getCameraDevice.return_value = CAM
    core_mock.getXYPosition.return_value = (0, 0)
    core_mock.getXPosition.return_value = 0
    core_mock.getYPosition.return_value = 0
    core_mock.getXYStageDevice.return_value = XYSTAGE
    core_mock.getFocusDevice.return_value = FOCUS
    core_mock.getFocusDevice.return_value = FOCUS
    core_mock.getPixelSizeUm.return_value = None
    core_mock.getNumberOfCameraChannels.return_value = 1
    core_mock.getImageBitDepth.return_value = 12
    core_mock.getNumberOfComponents.return_value = 1

    engine = MDAEngine(mmc=core_mock, use_hardware_sequencing=True)

    combined_events = list(engine.event_iterator(mda))
    assert len(combined_events) == 1
    seq_event = combined_events[0]
    assert isinstance(seq_event, SequencedEvent)

    runner = MDARunner()
    runner.set_engine(engine)
    runner.run(mda)

    n_img = prod(mda.shape)
    core_mock.startSequenceAcquisition.assert_called_once_with(n_img, 0, True)
    core_mock.loadExposureSequence.assert_called_once_with(
        CAM, seq_event.exposure_sequence
    )
    core_mock.loadXYStageSequence.assert_called_once_with(
        XYSTAGE, seq_event.x_sequence, seq_event.y_sequence
    )


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
def sequence_tester() -> CMMCorePlus:
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
