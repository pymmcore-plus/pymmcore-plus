from typing import Callable
from unittest.mock import Mock

import numpy as np
import pytest
import useq
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.metadata import (
    FrameMetaV1,
    SummaryMetaV1,
    frame_metadata,
    serialize,
    summary_metadata,
)


def test_create_schema() -> None:
    pytest.importorskip("msgspec")
    serialize.msgspec_to_schema(SummaryMetaV1)
    serialize.msgspec_to_schema(FrameMetaV1)


def test_from_core() -> None:
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    summary = summary_metadata(core)
    assert isinstance(summary, dict)
    frame = frame_metadata(core)
    assert isinstance(frame, dict)


@pytest.mark.parametrize(
    "dumps", [serialize.msgspec_json_dumps, serialize.std_json_dumps]
)
def test_metadata_during_mda(
    core: CMMCorePlus, dumps: Callable, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serialize, "json_dumps", dumps)
    seq = useq.MDASequence(
        channels=["DAPI", "FITC"],
        time_plan=useq.TIntervalLoops(interval=0.01, loops=2),
    )
    seq_started_mock = Mock()
    frame_ready_mock = Mock()

    core.mda.events.sequenceStarted.connect(seq_started_mock)
    core.mda.events.frameReady.connect(frame_ready_mock)

    core.mda.run(seq)

    seq_started_mock.assert_called_once()
    _seq, _meta = seq_started_mock.call_args.args
    assert _seq == seq
    assert isinstance(_meta, dict)
    assert _meta["format"] == "summary-dict-full"
    assert isinstance(_meta["mda_sequence"], useq.MDASequence)
    assert isinstance(dumps(_meta), bytes)

    frame_ready_mock.assert_called()
    _frame, _event, _meta = frame_ready_mock.call_args.args
    assert isinstance(_frame, np.ndarray)
    assert isinstance(_event, useq.MDAEvent)
    assert isinstance(_meta, dict)
    assert isinstance(dumps(_meta), bytes)
    assert _meta["format"] == "frame-dict-minimal"
    assert any(pv["dev"] == "Excitation" for pv in _meta["property_values"])
