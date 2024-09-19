from typing import Callable
from unittest.mock import Mock

import numpy as np
import pytest
import useq

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.metadata import (
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


DUMPS = [serialize.std_json_dumps]
if serialize.msgspec is not None:  # type: ignore
    DUMPS.append(serialize.msgspec_json_dumps)


@pytest.mark.parametrize("dumps", DUMPS)
def test_metadata_during_mda(
    core: CMMCorePlus, dumps: Callable, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serialize, "json_dumps", dumps)
    loader = getattr(serialize, dumps.__name__.replace("_dumps", "_loads"))
    to_builtins = getattr(
        serialize, dumps.__name__.replace("_json_dumps", "_to_builtins")
    )

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
    assert _meta["format"] == "summary-dict"
    assert isinstance(_meta["mda_sequence"], useq.MDASequence)
    dumped = dumps(_meta)
    assert isinstance(to_builtins(_meta), dict)
    assert isinstance(dumped, bytes)
    loaded = loader(dumped)
    assert isinstance(loaded, dict)

    frame_ready_mock.assert_called()
    _frame, _event, _meta = frame_ready_mock.call_args.args
    assert isinstance(_frame, np.ndarray)
    assert isinstance(_event, useq.MDAEvent)
    assert isinstance(_meta, dict)
    assert _meta["format"] == "frame-dict"
    assert any(pv["dev"] == "Excitation" for pv in _meta["property_values"])
    dumped = dumps(_meta, indent=2)
    assert isinstance(to_builtins(_meta), dict)
    assert isinstance(dumped, bytes)
    loaded = loader(dumped)
    assert isinstance(loaded, dict)


@pytest.mark.parametrize("sequenced", [True, False], ids=["sequenced", "not-sequenced"])
def test_multicam(core: CMMCorePlus, sequenced: bool) -> None:
    mc = "YoMulti"
    core.loadDevice("Camera2", "DemoCamera", "DCam")
    core.loadDevice(mc, "Utilities", "Multi Camera")
    core.initializeDevice(mc)
    core.initializeDevice("Camera2")
    core.setProperty("Camera2", "BitDepth", "16")
    core.setProperty(mc, "Physical Camera 1", "Camera")
    core.setProperty(mc, "Physical Camera 2", "Camera2")
    core.setCameraDevice(mc)

    mda = useq.MDASequence(
        channels=["Cy5", "FITC"],
        time_plan={"interval": 0, "loops": 3},
        axis_order="pctz",
        stage_positions=[(222, 1, 1), (111, 0, 0)],
    )

    summary_mock = Mock()
    frame_mock = Mock()

    core.mda.engine.use_hardware_sequencing = sequenced
    core.mda.events.sequenceStarted.connect(summary_mock)
    core.mda.events.frameReady.connect(frame_mock)
    core.mda.run(mda)

    assert summary_mock.call_count == 1
    assert frame_mock.call_count == len(list(mda)) * core.getNumberOfCameraChannels()
    for call in summary_mock.call_args_list:
        meta = call.args[1]
        assert meta["format"] == "summary-dict"
    time_stamps = []
    for call in frame_mock.call_args_list:
        meta = call.args[2]
        assert meta["format"] == "frame-dict"
        assert ("camera_metadata" in meta) is sequenced
        time_stamps.append(meta["runner_time_ms"])
