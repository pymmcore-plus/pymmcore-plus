from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import useq
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import mda_listeners_connected
from pymmcore_plus.mda.handlers import OMEZarrWriter

if TYPE_CHECKING:
    import zarr
else:
    zarr = pytest.importorskip("zarr")


def test_ome_tiff_writer(tmp_path: Path, core: CMMCorePlus) -> None:
    mda = useq.MDASequence(
        channels=["Cy5", "FITC"],
        time_plan={"interval": 0.1, "loops": 3},
        stage_positions=[(222, 1, 1), (111, 0, 0)],
        z_plan={"range": 0.3, "step": 0.1},
        axis_order="tpcz",
    )

    dest = tmp_path / "out.zarr"
    writer = OMEZarrWriter(dest)

    with mda_listeners_connected(writer, mda_events=core.mda.events):
        core.mda.run(mda)

    data = zarr.open(dest)
    no_p_shape = tuple(v for k, v in mda.sizes.items() if k != "p")
    assert data["p0"].shape == (*no_p_shape, 512, 512)
    assert data["p1"].shape == (*no_p_shape, 512, 512)
