from pathlib import Path
from typing import TYPE_CHECKING

from useq import MDASequence

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDATiffWriter

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def test_tiff_writer(core: CMMCorePlus, tmp_path: Path, qtbot: "QtBot"):
    mda = MDASequence(
        time_plan={"interval": 0.1, "loops": 2},
        stage_positions=[(1, 1, 1)],
        z_plan={"range": 3, "step": 1},
        channels=[{"config": "DAPI", "exposure": 1}],
    )
    writer = MDATiffWriter(str(tmp_path / "mda_data"))
    writer._on_mda_engine_registered(core.mda)

    # run twice to check that we aren't overwriting files
    with qtbot.waitSignal(core.mda.events.sequenceFinished):
        core.run_mda(mda)
    with qtbot.waitSignal(core.mda.events.sequenceFinished):
        core.run_mda(mda)

    # check that the correct folders/files were generated
    data_folders = set(map(str, tmp_path.glob("mda_data*")))
    expected = {str(tmp_path / "mda_data_1"), str(tmp_path / "mda_data_2")}

    assert expected.issubset(data_folders)
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
    actual_1 = list((tmp_path / "mda_data_1").glob("*"))
    actual_2 = list((tmp_path / "mda_data_2").glob("*"))
    for e in expected:
        assert tmp_path / "mda_data_1" / e in actual_1
        assert tmp_path / "mda_data_2" / e in actual_2
