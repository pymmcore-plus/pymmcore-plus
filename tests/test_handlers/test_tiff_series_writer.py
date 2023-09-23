import json
from math import prod
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
import useq
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import mda_listeners_connected
from pymmcore_plus.mda.handlers import TiffSeriesWriter

if TYPE_CHECKING:
    import tifffile as tf
else:
    tf = pytest.importorskip("tifffile")


def test_tiff_series_writer(tmp_path: Path, core: CMMCorePlus) -> None:
    mda = useq.MDASequence(
        channels=["Cy5", "FITC"],
        time_plan={"interval": 0.1, "loops": 3},
        stage_positions=[(222, 1, 1), (111, 0, 0)],
        z_plan={"range": 0.3, "step": 0.1},
        axis_order="tpcz",
    )

    dest = tmp_path / "out"
    writer = TiffSeriesWriter(dest, prefix="hello")

    with mda_listeners_connected(
        writer, mda_events=core.mda.events, asynchronous=False
    ):
        core.mda.run(mda)

    files_written = list(dest.glob("*.tif"))
    assert len(files_written) == prod(mda.shape)

    # we can use tiffile pattern='axes' to load the data in the correct
    # shape because write a filename pattern that tifffile recognizes (Leica tiff)
    data = tf.imread(f"{dest}/*.tif", pattern="axes")
    assert isinstance(data, np.ndarray)
    assert data.shape == (*mda.shape, 512, 512)

    # test metadata
    frame_meta = json.loads((dest / TiffSeriesWriter.FRAME_META_PATH).read_text())
    assert set(frame_meta) == {f.name for f in files_written}
    # we can recover the original MDASequence from the metadata
    assert useq.MDASequence.from_file(dest / TiffSeriesWriter.SEQ_META_PATH) == mda

    # test overwrite
    with pytest.raises(FileExistsError):
        TiffSeriesWriter(dest, prefix="hello", overwrite=False)

    TiffSeriesWriter(dest, prefix="hello", overwrite=True)
    assert not dest.exists()
