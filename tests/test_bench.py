from __future__ import annotations

import os
import sys
import time
from typing import TYPE_CHECKING, Any, Callable

import numpy as np
import pytest
import useq

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.experimental.unicore import CameraDevice
from pymmcore_plus.experimental.unicore.core._sequence_buffer import SequenceBuffer
from pymmcore_plus.experimental.unicore.core._unicore import UniMMCore

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from numpy.typing import DTypeLike

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


@pytest.fixture(scope="session", params=[(256, 256), (1024, 1024)])
def test_frame(request: Any) -> np.ndarray:
    """Reusable random frame."""
    rng = np.random.default_rng(seed=0)
    return rng.integers(0, 256, size=request.param, dtype=np.uint8)


def test_acquire_finalize_pop(test_frame: np.ndarray, benchmark: Callable) -> None:
    seqbuf = SequenceBuffer(size_mb=16.0, overwrite_on_overflow=True)
    out = np.empty_like(test_frame)

    def _producer_consumer() -> None:
        buf = seqbuf.acquire_slot(test_frame.shape, test_frame.dtype)
        # Simulate the camera filling the buffer (memcpy cost is part of reality)
        buf[:] = test_frame
        seqbuf.finalize_slot(None)
        seqbuf.pop_next(out=out)

    benchmark(_producer_consumer)


def test_insert_data(test_frame: np.ndarray, benchmark: Callable) -> None:
    seqbuf = SequenceBuffer(size_mb=16.0, overwrite_on_overflow=True)

    def _copy_path() -> None:
        seqbuf.acquire_slot(test_frame.shape, test_frame.dtype)[:] = test_frame
        seqbuf.finalize_slot()
        _ = seqbuf.pop_next()

    benchmark(_copy_path)


def test_overwrite_under_pressure(benchmark: Callable) -> None:
    tiny_buf = SequenceBuffer(size_mb=1.0, overwrite_on_overflow=True)
    frame = np.ones((600, 600), dtype=np.uint8)

    def _overwrite() -> None:
        tiny_buf.insert_data(frame, None)  # no pop: buffer stays full, evicts

    benchmark(_overwrite)


DEV = "Camera"
FRAME_SHAPE = (512, 512)
DTYPE = np.uint16
FRAME = np.ones(FRAME_SHAPE, dtype=DTYPE)


class MyCamera(CameraDevice):
    def get_exposure(self) -> float:
        return 100.0

    def set_exposure(self, exposure: float) -> None:
        pass

    def shape(self) -> tuple[int, int]:
        """Return the shape of the current camera state."""
        return FRAME_SHAPE

    def dtype(self) -> DTypeLike:
        """Return the data type of the current camera state."""
        return DTYPE

    def start_sequence(
        self, n: int, get_buffer: Callable[[Sequence[int], DTypeLike], np.ndarray]
    ) -> Iterator[Mapping]:
        """Start a sequence acquisition."""
        shape, dtype = self.shape(), self.dtype()
        for _ in range(n):
            time.sleep(0.001)
            get_buffer(shape, dtype)[:] = FRAME
            yield {}


@pytest.mark.parametrize("device", ["python", "c++"])
def test_bench_unicore_camera(device: str, benchmark: Callable) -> None:
    core = UniMMCore()
    if device == "python":
        core.loadPyDevice(DEV, MyCamera())
    else:
        core.loadDevice(DEV, "DemoCamera", "DCam")
    core.initializeAllDevices()
    core.setCameraDevice(DEV)
    core.setExposure(1)

    def _burst() -> None:
        core.startSequenceAcquisition(20, 0, True)
        while core.getRemainingImageCount():
            core.popNextImage()
        core.stopSequenceAcquisition()

    benchmark(_burst)
