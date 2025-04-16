from __future__ import annotations

from queue import Queue
from typing import TYPE_CHECKING

import numpy as np
import pytest
import useq

from pymmcore_plus.mda.handlers import OMEZarrWriter, TensorStoreHandler
from pymmcore_plus.metadata import serialize

if TYPE_CHECKING:
    from pathlib import Path

    import zarr
    import zarr.storage

    from pymmcore_plus import CMMCorePlus
else:
    zarr = pytest.importorskip("zarr")
    import zarr.storage  # noqa: F811

try:
    import xarray as xr
except ImportError:
    xr = None

try:
    import tensorstore as ts
except ImportError:
    ts = None

requires_tensorstore = pytest.mark.skipif(not ts, reason="requires tensorstore")

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
GRID_MDA = SIMPLE_MDA.replace(
    grid_plan={"rows": 2, "columns": 2, "mode": "row_wise_snake"},
)
GRID_EXPECTATION = {
    "p0": {"t": 2, "c": 2, "y": 512, "x": 512},
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


CASES: list[str | None, useq.MDASequence, dict[str, dict]] = [
    (None, SIMPLE_MDA, SIMPLE_EXPECTATION),
    (None, MULTIPOINT_MDA, MULTIPOINT_EXPECTATION),
    (None, GRID_MDA, GRID_EXPECTATION),
    (None, FULL_MDA, FULL_EXPECTATION),
    ("out.zarr", FULL_MDA, FULL_EXPECTATION),
    (None, FULL_MDA, FULL_EXPECTATION),
    ("tmp", FULL_MDA, FULL_EXPECTATION),
    (None, COMPLEX_MDA, COMPLEX_EXPECTATION),
]


@pytest.mark.parametrize("store, mda, expected_shapes", CASES)
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
        for k, ary in data.arrays():
            if k in writer.position_arrays:
                # ensure real data was written
                assert ary.nchunks_initialized > 0
                assert ary[0, 0].mean() > ary.fill_value
    else:
        data = writer.group

    # check that arrays have expected shape and dimensions
    for k, v in data.arrays():
        if k not in writer.position_arrays:
            continue  # not a position array

        actual_shape = dict(zip(v.attrs["_ARRAY_DIMENSIONS"], v.shape))
        assert expected_shapes[k] == actual_shape

        # check that the MDASequence was stored
        stored_seq = useq.MDASequence.model_validate(v.attrs["useq_MDASequence"])
        assert stored_seq == mda

        if xr is not None:
            # check that the xarray was written
            ds = writer.as_xarray()
            assert isinstance(ds, xr.Dataset)
            assert ds[k].sizes == expected_shapes[k]
            # check that *most* dimensions have coordinates
            for dim_name in ds.dims:
                if dim_name != "g":
                    assert dim_name in ds.coords

    # smoke test the isel method
    assert isinstance(writer.isel(p=0, t=0, x=slice(0, 100)), np.ndarray)


@requires_tensorstore
@pytest.mark.parametrize("store, mda, expected_shapes", CASES)
def test_tensorstore_writer(
    store: str | None,
    mda: useq.MDASequence,
    expected_shapes: dict[str, dict],
    tmp_path: Path,
    core: CMMCorePlus,
) -> None:
    if store == "tmp":
        writer = TensorStoreHandler.in_tmpdir()
    elif store is None:
        writer = TensorStoreHandler()
    else:
        writer = TensorStoreHandler(path=tmp_path / store)

    core.mda.run(mda, output=writer)

    assert writer.store is not None

    expected_sizes = {}
    for sizes in expected_shapes.values():
        for dim, size in sizes.items():
            expected_sizes[dim] = max(sizes.get(dim, 0), size)
    if len(expected_shapes) > 1:
        expected_sizes["p"] = len(expected_shapes)

    sizes = dict(zip(writer.store.domain.labels, writer.store.shape))
    assert sizes == expected_sizes

    if store_path := getattr(writer.store.kvstore, "path", None):
        # ensure that non-memory stores were written to disk
        ary = zarr.open(store_path)
        # ensure real data was written
        assert ary.nchunks_initialized > 0
        assert ary[0, 0].mean() > (ary.fill_value or 0)

    # smoke test the isel method
    x = writer.isel(t=0, c=0, x=slice(0, 100))
    assert isinstance(x, np.ndarray)
    assert x.shape[-1] == 100


@requires_tensorstore
def test_tensorstore_writer_spec_override(
    tmp_path: Path,
) -> None:
    writer = TensorStoreHandler(
        path=tmp_path / "test.zarr",
        spec={"context": {"cache_pool": {"total_bytes_limit": 10000000}}},
    )

    assert writer.get_spec()["context"]["cache_pool"]["total_bytes_limit"] == 10000000


@requires_tensorstore
@pytest.mark.parametrize("dumps", ["msgspec", "std"])
def test_tensorstore_writes_metadata(
    tmp_path: Path,
    core: CMMCorePlus,
    dumps: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that we can write metadata with or without msgspec."""
    from pymmcore_plus.mda.handlers import _tensorstore_handler

    if dumps == "msgspec":
        pytest.importorskip("msgspec")

    dumper = getattr(serialize, f"{dumps}_json_dumps")
    loader = getattr(serialize, f"{dumps}_json_loads")
    monkeypatch.setattr(_tensorstore_handler, "json_dumps", dumper)
    monkeypatch.setattr(_tensorstore_handler, "json_loads", loader)
    writer = TensorStoreHandler(path=tmp_path / "test.zarr")
    core.mda.run(SIMPLE_MDA, output=writer)

    zarr_store = zarr.open(str(tmp_path / "test.zarr"))
    assert hasattr(zarr_store, "attrs")
    assert "frame_metadatas" in zarr_store.attrs, (
        "Missing frame_metadatas in zarr attributes"
    )


@requires_tensorstore
def test_tensorstore_writer_indeterminate(tmp_path: Path, core: CMMCorePlus) -> None:
    # FIXME: this test is actually throwing difficult-to-debug exceptions
    # when driver=='zarr'.  It happens when awaiting the result of self._store.resize()
    # inside of sequenceFinished.
    writer = TensorStoreHandler()

    que = Queue()
    thread = core.run_mda(iter(que.get, None), output=writer)
    for t in range(2):
        for z in range(2):
            que.put(useq.MDAEvent(index={"t": t, "z": z, "c": 0}))
    que.put(None)
    thread.join()

    assert writer.isel(t=1, z=1, c=0).shape == (512, 512)
    assert writer.isel(t=1, z=slice(None), c=0).shape == (2, 512, 512)
    with pytest.raises(KeyError):
        writer.isel(t=2, z=2, c=0)
