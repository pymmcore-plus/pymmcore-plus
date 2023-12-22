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

full_mda = useq.MDASequence(
        channels=["Cy5", "FITC"],
        time_plan={"interval": 0.1, "loops": 3},
        stage_positions=[(222, 1, 1), (111, 0, 0)],
        z_plan={"range": 0.3, "step": 0.1},
        axis_order="tpcz",
    )

part_mda = useq.MDASequence(
        channels=["Cy5", "FITC"],
        time_plan={"interval": 0.1, "loops": 3},
    )

@pytest.mark.parametrize("store, mda", [("out.zarr", full_mda), (None, full_mda), ("tmp", full_mda),
                                        (None, part_mda)])
def test_ome_zarr_writer(store: str | None,
                         mda: useq.MDASequence,
                         tmp_path: Path,
                         core: CMMCorePlus) -> None:

    if store == "tmp":
        writer = OMEZarrWriter.in_tmpdir()
    elif store is None:
        writer = OMEZarrWriter()
    else:
        writer = OMEZarrWriter(tmp_path / store)

    with mda_listeners_connected(writer, mda_events=core.mda.events):
        core.mda.run(mda)

    no_p_shape = tuple(v for k, v in mda.sizes.items() if k != "p")
    expected_shape = (*no_p_shape, 512, 512)

    actual_shapes = {k: v.shape for k, v in writer.group.arrays()}
    assert actual_shapes == {"p0": expected_shape, "p1": expected_shape}

    if store:
        # check that non-memory stores were written to disk
        data = zarr.open(writer.group.store.path)
        actual_shapes = {k: v.shape for k, v in data.arrays()}
        assert actual_shapes == {"p0": expected_shape, "p1": expected_shape}

        p0 = data["p0"]
        assert p0[0, 0, 0].mean() > p0.fill_value  # real data was written
