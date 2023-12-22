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


SIMPLE_MDA = useq.MDASequence(
    channels=["Cy5", "FITC"],
    time_plan={"interval": 0.1, "loops": 2},
    axis_order="tpcz",
)
SIMPLE_EXPECTATION = {"p0": {"shape": (2, 2, 512, 512), "axes": ["t", "c"]}}

MULTIPOINT_MDA = SIMPLE_MDA.replace(
    channels=["Cy5", "FITC"],
    stage_positions=[(222, 1, 1), (111, 0, 0)],
    time_plan={"interval": 0.1, "loops": 2},
)
MULTIPOINT_EXPECTATION = {
    "p0": {"shape": (2, 2, 512, 512), "axes": ["t", "c"]},
    "p1": {"shape": (2, 2, 512, 512), "axes": ["t", "c"]},
}

FULL_MDA = MULTIPOINT_MDA.replace(z_plan={"range": 0.3, "step": 0.1})
FULL_EXPECTATION = {
    "p0": {"shape": (2, 2, 4, 512, 512), "axes": ["t", "c", "z"]},
    "p1": {"shape": (2, 2, 4, 512, 512), "axes": ["t", "c", "z"]},
}

COMPLEX_MDA = FULL_MDA.replace(
    stage_positions=[
        (222, 1, 1),
        {
            "x": 0,
            "y": 0,
            "sequence": useq.MDASequence(
                grid_plan={"rows": 2, "columns": 1},
                z_plan={"range": 3, "step": 1},
            ),
        },
    ]
)
COMPLEX_EXPECTATION = {
    "p0": {"shape": (2, 2, 4, 512, 512), "axes": ["t", "c", "z"]},
    "p1": {"shape": (2, 4, 2, 2, 512, 512), "axes": ["g", "z", "t", "c"]},
}


@pytest.mark.parametrize(
    "store, mda, expected_shapes",
    [
        (None, SIMPLE_MDA, SIMPLE_EXPECTATION),
        (None, MULTIPOINT_MDA, MULTIPOINT_EXPECTATION),
        (None, FULL_MDA, FULL_EXPECTATION),
        ("out.zarr", FULL_MDA, FULL_EXPECTATION),
        (None, FULL_MDA, FULL_EXPECTATION),
        ("tmp", FULL_MDA, FULL_EXPECTATION),
        (None, COMPLEX_MDA, COMPLEX_EXPECTATION),
    ],
)
def test_ome_zarr_writer(
    store: str | None,
    mda: useq.MDASequence,
    expected_shapes: dict[str, dict],
    tmp_path: Path,
    core: CMMCorePlus,
) -> None:
    if store == "tmp":
        writer = OMEZarrWriter.in_tmpdir()
    elif store is None:
        writer = OMEZarrWriter()
    else:
        writer = OMEZarrWriter(tmp_path / store)

    with mda_listeners_connected(writer, mda_events=core.mda.events):
        core.mda.run(mda)

    if store:
        # ensure that non-memory stores were written to disk
        data = zarr.open(writer.group.store.path)
        for _, ary in data.arrays():
            # ensure real data was written
            assert ary.nchunks_initialized > 0
            assert ary[0, 0].mean() > ary.fill_value
    else:
        data = writer.group

    actual_shapes = {
        k: {"shape": v.shape, "axes": v.attrs["_ARRAY_DIMENSIONS"]}
        for k, v in data.arrays()
    }
    assert actual_shapes == expected_shapes
