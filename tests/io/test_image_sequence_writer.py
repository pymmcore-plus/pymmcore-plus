import json
from math import prod
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock

import numpy as np
import pytest
import useq

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import mda_listeners_connected
from pymmcore_plus.mda.handlers import ImageSequenceWriter

if TYPE_CHECKING:
    import tifffile as tf  # noqa


def test_tiff_sequence_writer(tmp_path: Path, core: CMMCorePlus) -> None:
    tf = pytest.importorskip("tifffile")
    mda = useq.MDASequence(
        channels=["Cy5", "FITC"],
        time_plan={"interval": 0.1, "loops": 3},
        stage_positions=[(222, 1, 1), (111, 0, 0)],
        z_plan={"range": 0.3, "step": 0.1},
        axis_order="tpcz",
    )

    dest = tmp_path / "out"
    core.mda.run(mda, output=dest)

    files_written = list(dest.glob("*.tif"))
    assert len(files_written) == prod(mda.shape)

    # we can use tifffile pattern='axes' to load the data in the correct
    # shape because write a filename pattern that tifffile recognizes (Leica tiff)
    data = tf.imread(f"{dest}/*.tif", pattern="axes")
    assert isinstance(data, np.ndarray)
    assert data.shape == (*mda.shape, 512, 512)

    # test metadata
    frame_meta = json.loads((dest / ImageSequenceWriter.FRAME_META_PATH).read_text())
    assert set(frame_meta) == {f.name for f in files_written}
    # we can recover the original MDASequence from the metadata
    assert useq.MDASequence.from_file(dest / ImageSequenceWriter.SEQ_META_PATH) == mda

    # test overwrite
    with pytest.raises(FileExistsError):
        ImageSequenceWriter(dest, prefix="hello", overwrite=False)

    ImageSequenceWriter(dest, prefix="hello", overwrite=True)
    assert not dest.exists()


def test_tiff_with_subseries(tmp_path: Path, core: CMMCorePlus) -> None:
    tf = pytest.importorskip("tifffile")
    subseq = useq.MDASequence(grid_plan=useq.GridRowsColumns(rows=1, columns=3))
    mda = useq.MDASequence(
        channels=["Cy5"],
        stage_positions=[(222, 1, 1), useq.Position(x=111, sequence=subseq)],
    )

    dest = tmp_path / "out"
    writer = ImageSequenceWriter(dest)

    with mda_listeners_connected(
        writer, mda_events=core.mda.events, asynchronous=False
    ):
        core.mda.run(mda)

    files_written = list(dest.glob("*.tif"))
    assert len(files_written) == len(list(mda))
    # we can use tifffile pattern='axes' to load the data in the correct
    # shape because write a filename pattern that tifffile recognizes (Leica tiff)
    # 00004_p001_c01_g000.tif

    data = tf.imread(f"{dest}/*.tif", pattern=r"_(p)(\d+)_(c)(\d+)_(g)(\d+)")
    assert isinstance(data, np.ndarray)
    assert data.shape[:-2] == (2, 1, 3)  # 2 positions, 1 channel, 3 grid positions

    # note that when loading this way... some of the frames will be empty
    # it's not critical to test it, but this would be True:
    # assert np.array_equal(data[0, 0, 1], np.zeros((512, 512)))  # no grid on pos 1


def test_any_writer(tmp_path: Path, core: CMMCorePlus) -> None:
    mda = useq.MDASequence(
        channels=["Cy5", "FITC"], time_plan={"interval": 0.1, "loops": 10}
    )

    mock = Mock()
    dest = tmp_path / "out"
    writer = ImageSequenceWriter(dest, imwrite=mock)

    with mda_listeners_connected(
        writer, mda_events=core.mda.events, asynchronous=False
    ):
        core.mda.run(mda)

    assert mock.call_count == prod(mda.shape)
    fname, ary = mock.call_args_list[0][0]
    assert isinstance(fname, str)
    assert str(tmp_path) in fname
    assert isinstance(ary, np.ndarray)
