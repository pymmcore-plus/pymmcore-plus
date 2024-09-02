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

seq1 = useq.MDASequence(
    channels=["Cy5", "FITC"],
    time_plan={"interval": 0.1, "loops": 3},
    stage_positions=[(222, 1, 1), (111, 0, 0)],
    z_plan={"range": 0.3, "step": 0.1},
    axis_order="tpcz",
)

seq2 = useq.MDASequence(
    channels=["FITC"],
    time_plan={"interval": 0.2, "loops": 3},
    axis_order="tc",
)

seq3 = useq.MDASequence(
    channels=["FITC"],
    stage_positions=[(222, 1, 1), (111, 0, 0)],
    time_plan={"interval": 0.2, "loops": 3},
    axis_order="ptc",
)


@pytest.mark.parametrize("ome", [True, False])
@pytest.mark.parametrize("seq", [seq1, seq2, seq3])
def test_ome_tiff_writer(
    ome: bool, tmp_path: Path, core: CMMCorePlus, seq: useq.MDASequence
) -> None:
    # whether .ome. appears in the filename determines whether tifffile
    # will write OME-TIFF or not

    dest = tmp_path / ("out.ome.tiff" if ome else "out.tiff")
    writer = OMETiffWriter(dest)

    with mda_listeners_connected(
        writer, mda_events=core.mda.events, asynchronous=False
    ):
        core.mda.run(seq)

    # multi-position sequences will be split into multiple files
    n_positions = seq.sizes.get("p", 1)
    if n_positions > 1:
        ext = ".ome.tif" if ome else ".tif"
        files = [str(dest).replace(ext, f"_p{i}{ext}") for i in range(n_positions)]
    else:
        files = [str(dest)]

    # check that the files exist and have the correct shape
    for file in files:
        assert Path(file).exists()
        data = cast("np.ndarray", tf.imread(file))

        # the expected shape will depend on whether it's OME or not.
        # imageJ output is always in "tzcyx" order, while OME will follow the experiment
        dims = list(seq.sizes) if ome else "tzcyxs"
        seq_shape = tuple(
            size for ax in dims if ax != "p" and (size := seq.sizes.get(ax, 0)) > 1
        )

        assert data.shape[:-2] == seq_shape
