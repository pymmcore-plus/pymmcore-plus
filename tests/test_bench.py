from __future__ import annotations

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
T10 = useq.TIntervalLoops(interval=0, loops=10)  # type: ignore
T40 = useq.TIntervalLoops(interval=0, loops=40)  # type: ignore
T200 = useq.TIntervalLoops(interval=0, loops=200)  # type: ignore
DAPI = useq.Channel(config="DAPI", exposure=MIN_EXPOSURE)
FITC = useq.Channel(config="FITC", exposure=MIN_EXPOSURE)
RHOD = useq.Channel(config="Rhodamine", exposure=MIN_EXPOSURE)
CY5 = useq.Channel(config="Cy5", exposure=MIN_EXPOSURE)
C1 = (DAPI,)
C4 = (DAPI, FITC, RHOD, CY5)
P1 = (useq.Position(x=0, y=0, z=0),)
P20 = tuple(useq.Position(x=i, y=i, z=i) for i in range(20))
P100 = tuple(useq.Position(x=i, y=i, z=i) for i in range(100))
Z10 = useq.ZRangeAround(range=10, step=1)
Z40 = useq.ZRangeAround(range=40, step=1)
Z200 = useq.ZRangeAround(range=200, step=1)


MDAS = {
    "z10": useq.MDASequence(z_plan=Z10),
    "z200": useq.MDASequence(z_plan=Z200),
    "t10": useq.MDASequence(time_plan=T10),
    "t200": useq.MDASequence(time_plan=T200),
    "c1": useq.MDASequence(channels=C1),
    "c4": useq.MDASequence(channels=C4),
    "p1": useq.MDASequence(stage_positions=P1),
    "p100": useq.MDASequence(stage_positions=P100),
    "t10p1c1z10": useq.MDASequence(
        z_plan=Z10, time_plan=T10, channels=C1, stage_positions=P1, axis_order="tpcz"
    ),
    "z10c1p1t10": useq.MDASequence(
        z_plan=Z10, time_plan=T10, channels=C1, stage_positions=P1, axis_order="zcpt"
    ),
    "t40p20c4z40": useq.MDASequence(
        z_plan=Z40, time_plan=T40, channels=C4, stage_positions=P20, axis_order="tpcz"
    ),
}


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
