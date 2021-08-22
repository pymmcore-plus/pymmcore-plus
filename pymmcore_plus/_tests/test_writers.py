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


def test_tiff_writer(core: CMMCorePlus, tmp_path: Path):
    mda = MDASequence(
        time_plan={"interval": 0.1, "loops": 2},
        stage_positions=[(1, 1, 1)],
        z_plan={"range": 3, "step": 1},
        channels=[{"config": "DAPI", "exposure": 1}],
    )
    writer = MDA_multifile_tiff_writer(str(tmp_path / "mda_data"))

    # run twice to check that we aren't overwriting files
    core.run_mda(mda, writer)
    core.run_mda(mda, writer)

    # check that the correct folders/files were generated
    data_folders = set(tmp_path.glob("mda_data*"))
    assert {tmp_path / "mda_data", tmp_path / "mda_data_1"}.issubset(set(data_folders))
    expected = [
        Path("t000_p000_c000_z000.tiff"),
        Path("t001_p000_c000_z000.tiff"),
        Path("t001_p000_c000_z002.tiff"),
        Path("t001_p000_c000_z001.tiff"),
        Path("t000_p000_c000_z001.tiff"),
        Path("t001_p000_c000_z003.tiff"),
        Path("t000_p000_c000_z002.tiff"),
        Path("t000_p000_c000_z003.tiff"),
    ]
    actual_1 = list((tmp_path / "mda_data").glob("*"))
    actual_2 = list((tmp_path / "mda_data_1").glob("*"))
    for e in expected:
        assert tmp_path / "mda_data" / e in actual_1
        assert tmp_path / "mda_data_1" / e in actual_2
