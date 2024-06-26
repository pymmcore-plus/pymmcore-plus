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
    assert _meta["format"] == "summary-dict-full"
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
    assert _meta["format"] == "frame-dict-minimal"
    assert any(pv["dev"] == "Excitation" for pv in _meta["property_values"])
    dumped = dumps(_meta, indent=2)
    assert isinstance(to_builtins(_meta), dict)
    assert isinstance(dumped, bytes)
    loaded = loader(dumped)
    assert isinstance(loaded, dict)


def test_multicam(core: CMMCorePlus) -> None:
    mc = "YoMulti"
    core.loadDevice("Camer2", "DemoCamera", "DCam")
    core.loadDevice(mc, "Utilities", "Multi Camera")
    core.initializeDevice(mc)
    core.initializeDevice("Camer2")
    core.setProperty("Camer2", "BitDepth", "16")
    core.setProperty(mc, "Physical Camera 1", "Camera")
    core.setProperty(mc, "Physical Camera 2", "Camer2")
    core.setCameraDevice(mc)
    breakpoint()
    mda = useq.MDASequence(
        channels=["Cy5", "FITC"],
        time_plan={"interval": 0, "loops": 3},
        axis_order="tpcz",
        stage_positions=[(222, 1, 1), (111, 0, 0)],
    )

    Mock()
    Mock()
    from rich import print

    # core.mda.engine.use_hardware_sequencing = True
    core.mda.events.sequenceStarted.connect(print)
    core.mda.events.frameReady.connect(print)
    core.mda.run(mda)
