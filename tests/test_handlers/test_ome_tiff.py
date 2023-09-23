from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
import useq
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import mda_listeners_connected
from pymmcore_plus.mda.handlers import OMETiffWriter

if TYPE_CHECKING:
    import numpy as np
    import tifffile as tf
else:
    tf = pytest.importorskip("tifffile")


def test_ome_tiff_writer(tmp_path: Path, core: CMMCorePlus) -> None:
    mda = useq.MDASequence(
        channels=["Cy5", "FITC"],
        time_plan={"interval": 0.1, "loops": 3},
        stage_positions=[(222, 1, 1), (111, 0, 0)],
        z_plan={"range": 0.3, "step": 0.1},
        axis_order="tpcz",
    )

    dest = tmp_path / "out.ome.tiff"
    writer = OMETiffWriter(dest)

    with mda_listeners_connected(writer, mda_events=core.mda.events):
        core.mda.run(mda)

    data = cast("np.ndarray", tf.imread(dest))
    assert data.shape == (*mda.shape, 512, 512)
