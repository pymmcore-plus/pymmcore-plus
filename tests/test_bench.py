from __future__ import annotations

import os
import sys
from typing import Callable

import pytest
import useq
from pymmcore_plus import CMMCorePlus

if all(x not in {"--codspeed", "tests/test_bench.py"} for x in sys.argv):
    pytest.skip(
        "use 'pytest tests/test_bench.py' to run benchmark", allow_module_level=True
    )

MIN_EXPOSURE = 0.001
T5 = useq.TIntervalLoops(interval=0, loops=5)  # type: ignore
T20 = useq.TIntervalLoops(interval=0, loops=20)  # type: ignore
T200 = useq.TIntervalLoops(interval=0, loops=200)  # type: ignore
DAPI = useq.Channel(config="DAPI", exposure=MIN_EXPOSURE)
FITC = useq.Channel(config="FITC", exposure=MIN_EXPOSURE)
RHOD = useq.Channel(config="Rhodamine", exposure=MIN_EXPOSURE)
CY5 = useq.Channel(config="Cy5", exposure=MIN_EXPOSURE)
C1 = (DAPI,)
C4 = (DAPI, FITC, RHOD, CY5)
P1 = (useq.Position(x=0, y=0, z=0),)
P10 = tuple(useq.Position(x=i, y=i, z=i) for i in range(10))
P100 = tuple(useq.Position(x=i, y=i, z=i) for i in range(100))
Z5 = useq.ZRangeAround(range=5, step=1)
Z40 = useq.ZRangeAround(range=40, step=1)
Z200 = useq.ZRangeAround(range=200, step=1)


CI_MDAS = {
    "z40": useq.MDASequence(z_plan=Z40),
    "t20": useq.MDASequence(time_plan=T20),
    "c4": useq.MDASequence(channels=C4),
    "p10": useq.MDASequence(stage_positions=P10),
    "t5p1c4z5": useq.MDASequence(
        z_plan=Z5, time_plan=T5, channels=C4, stage_positions=P1, axis_order="tpcz"
    ),
}
# some of these are too slow to run in a reasonable amount of time on CI
ALL_MDAS = {
    **CI_MDAS,
    "z200": useq.MDASequence(z_plan=Z200),
    "t200": useq.MDASequence(time_plan=T200),
    "c1": useq.MDASequence(channels=C1),
    "p1": useq.MDASequence(stage_positions=P1),
    "z5c1p1t5": useq.MDASequence(
        z_plan=Z5, time_plan=T5, channels=C1, stage_positions=P1, axis_order="zcpt"
    ),
    "t40p10c4z40": useq.MDASequence(
        z_plan=Z40, time_plan=T20, channels=C4, stage_positions=P10, axis_order="tpcz"
    ),
}


MDAS = CI_MDAS if os.getenv("CI") else ALL_MDAS


@pytest.fixture
def core(caplog: pytest.LogCaptureFixture) -> CMMCorePlus:
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    caplog.set_level("CRITICAL")
    return core


@pytest.mark.parametrize("mda_key", MDAS)
def test_run_mda(mda_key: str, core: CMMCorePlus, benchmark: Callable) -> None:
    """Benchmark running MDA sequences."""
    seq = list(MDAS[mda_key])  # expand iterator prior to benchmarking
    benchmark(core.mda.run, seq)


def test_mda_summary_metadata(benchmark: Callable) -> None:
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    seq = useq.MDASequence()
    benchmark(core.mda.engine.setup_sequence, seq)  # type: ignore


def test_mda_frame_metadata(benchmark: Callable) -> None:
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    event = useq.MDAEvent()
    benchmark(core.mda.engine.exec_event, event)  # type: ignore
