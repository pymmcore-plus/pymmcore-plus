from __future__ import annotations

from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock, call

import useq
from pymmcore_plus.core._sequencing import get_all_sequenceable
from pymmcore_plus.mda import MDAEngine, MDARunner

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


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
    assert core_mock.setConfig.call_args_list == [
        call("Channel", "DAPI"),
        call("Channel", "FITC"),
        call("Channel", "DAPI"),
        call("Channel", "FITC"),
    ]
