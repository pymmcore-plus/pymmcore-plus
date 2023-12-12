from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import useq

from pymmcore_plus.mda import mda_listeners_connected
from pymmcore_plus.mda.handlers import OMEZarrWriter

if TYPE_CHECKING:
    from pathlib import Path

    import zarr

    from pymmcore_plus import CMMCorePlus
else:
    zarr = pytest.importorskip("zarr")


@pytest.mark.parametrize("store", ["out.zarr", None, "tmp"])
def test_ome_zarr_writer(store: str | None, tmp_path: Path, core: CMMCorePlus) -> None:
    mda = useq.MDASequence(
        channels=["Cy5", "FITC"],
        time_plan={"interval": 0.1, "loops": 2},
        stage_positions=[
            (222, 1, 1),
            {
                "x": 0,
                "y": 0,
                "sequence": useq.MDASequence(
                    grid_plan=useq.GridRowsColumns(rows=2, columns=1),
                    z_plan={"range": 3, "step": 1},
                ),
            },
        ],
        z_plan={"range": 0.3, "step": 0.1},
        axis_order="tpcz",
    )

    if store == "tmp":
        writer = OMEZarrWriter.in_tmpdir()
    elif store is None:
        writer = OMEZarrWriter()
    else:
        writer = OMEZarrWriter(tmp_path / store)

    with mda_listeners_connected(writer, mda_events=core.mda.events):
        core.mda.run(mda)

    expected_shape = {"p0": (2, 2, 4, 512, 512), "p1": (2, 4, 2, 2, 512, 512)}

    actual_shapes = {k: v.shape for k, v in writer.group.arrays()}
    assert actual_shapes == expected_shape

    if store:
        # check that non-memory stores were written to disk
        data = zarr.open(writer.group.store.path)
        actual_shapes = {k: v.shape for k, v in data.arrays()}
        assert actual_shapes == expected_shape

        p0 = data["p0"]
        assert p0[0, 0, 0].mean() > p0.fill_value  # real data was written
        assert p0.attrs["_ARRAY_DIMENSIONS"] == ["t", "c", "z"]

        p1 = data["p1"]
        assert p1[0, 0, 0].mean() > p1.fill_value
        assert p1.attrs["_ARRAY_DIMENSIONS"] == ["g", "z", "t", "c"]
