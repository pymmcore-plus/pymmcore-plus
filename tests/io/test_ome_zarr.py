from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import useq
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
SIMPLE_EXPECTATION = {"p0": {"t": 2, "c": 2, "y": 512, "x": 512}}

MULTIPOINT_MDA = SIMPLE_MDA.replace(
    channels=["Cy5", "FITC"],
    stage_positions=[(222, 1, 1), (111, 0, 0)],
    time_plan={"interval": 0.1, "loops": 2},
)
MULTIPOINT_EXPECTATION = {
    "p0": {"t": 2, "c": 2, "y": 512, "x": 512},
    "p1": {"t": 2, "c": 2, "y": 512, "x": 512},
}

FULL_MDA = MULTIPOINT_MDA.replace(z_plan={"range": 0.3, "step": 0.1})
FULL_EXPECTATION = {
    "p0": {"t": 2, "c": 2, "z": 4, "y": 512, "x": 512},
    "p1": {"t": 2, "c": 2, "z": 4, "y": 512, "x": 512},
}

COMPLEX_MDA = FULL_MDA.replace(
    channels=["Cy5"],
    time_plan={"interval": 0.1, "loops": 3},
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
    ],
)
COMPLEX_EXPECTATION = {
    "p0": {"t": 3, "c": 1, "z": 4, "y": 512, "x": 512},
    "p1": {"t": 3, "g": 2, "c": 1, "z": 4, "y": 512, "x": 512},
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

    core.mda.run(mda, output=writer)

    if store:
        # ensure that non-memory stores were written to disk
        data = zarr.open(writer.group.store.path)
        for _, ary in data.arrays():
            # ensure real data was written
            assert ary.nchunks_initialized > 0
            assert ary[0, 0].mean() > ary.fill_value
    else:
        data = writer.group

    # check that arrays have expected shape and dimensions
    actual_shapes = {
        k: dict(zip(v.attrs["_ARRAY_DIMENSIONS"], v.shape)) for k, v in data.arrays()
    }
    assert actual_shapes == expected_shapes

    # check that the MDASequence was stored
    for _, v in data.arrays():
        stored_seq = useq.MDASequence.parse_obj(v.attrs["useq_MDASequence"])
        assert stored_seq == mda


def test_ome_zarr_writer_pos_name(tmp_path: Path, core: CMMCorePlus) -> None:
    dest = tmp_path / "out.ome.zarr"
    writer = OMEZarrWriter(dest)

    seq = useq.MDASequence(
        axis_order="pc",
        channels=["FITC"],
        stage_positions=[
            {"x": 222, "y": 1, "z": 1, "name": "test_name_000"},
            {"x": 111, "y": 0, "z": 0, "name": ""},
            {"x": 111, "y": 0, "z": 0},
        ],
    )

    core.mda.run(seq, output=writer)

    assert (dest / "test_name_000").exists()
    assert (dest / "p1").exists()
    assert (dest / "p2").exists()
