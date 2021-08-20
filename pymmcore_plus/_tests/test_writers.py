from pathlib import Path

import pytest
from useq import MDASequence

from pymmcore_plus import CMMCorePlus, MDA_multifile_tiff_writer


@pytest.fixture
def core():
    core = CMMCorePlus()
    if not core.getDeviceAdapterSearchPaths():
        pytest.fail(
            "To run tests, please install MM with `python -m pymmcore_plus.install`"
        )
    core.loadSystemConfiguration("demo")
    return core


def test_tiff_writer(core: CMMCorePlus):
    mda = MDASequence(
        time_plan={"interval": 0.1, "loops": 2},
        stage_positions=[(1, 1, 1)],
        z_plan={"range": 3, "step": 1},
        channels=[{"config": "DAPI", "exposure": 1}],
    )
    writer = MDA_multifile_tiff_writer("mda_data")
    core.run_mda(mda, writer)
    core.run_mda(mda, writer)
    data_folders = [str(p) for p in Path(".").glob("mda_data*")]
    assert {"mda_data", "mda_data_1"}.issubset(set(data_folders))
