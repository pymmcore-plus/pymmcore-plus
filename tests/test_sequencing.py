from math import prod
from typing import cast
from unittest.mock import MagicMock, call

import useq
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.core._sequencing import SequencedEvent, get_all_sequenceable
from pymmcore_plus.mda import MDAEngine, MDARunner


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

    events = list(engine.event_iterator(mda))
    assert len(events) == EXPECTED_SEQUENCES

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


def test_fully_sequenceable_core():
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
    core_mock.isBufferOverflowed.return_value = False
    core_mock.getCameraDevice.return_value = CAM
    core_mock.getXYStageDevice.return_value = XYSTAGE
    core_mock.getFocusDevice.return_value = FOCUS
    core_mock.getFocusDevice.return_value = FOCUS
    core_mock.getPixelSizeUm.return_value = None

    engine = MDAEngine(mmc=core_mock)

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
