"""Tests for OMEWriterHandler."""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

import pytest
import useq

from pymmcore_plus.mda.handlers import OMEWriterHandler

if TYPE_CHECKING:
    from pathlib import Path

    from pymmcore_plus import CMMCorePlus

# Skip all tests if ome-writers is not installed
pytest.importorskip("ome_writers")


# -----------------------------------------------------------------------------
# MDA Sequences
# -----------------------------------------------------------------------------

SIMPLE_MDA = useq.MDASequence(
    channels=["Cy5", "FITC"],
    time_plan={"interval": 0.1, "loops": 2},
    axis_order="tpcz",
)

MULTIPOINT_MDA = SIMPLE_MDA.replace(
    stage_positions=[(222, 1, 1), (111, 0, 0)],
)

GRID_MDA = SIMPLE_MDA.replace(
    grid_plan={"rows": 2, "columns": 2, "mode": "row_wise_snake"},
)

GRID_MDA_SUBSEQUENCE = SIMPLE_MDA.replace(
    stage_positions=[
        (222, 1, 1),
        useq.Position(
            x=223,
            y=2,
            z=1,
            sequence=useq.MDASequence(grid_plan={"rows": 1, "columns": 2}),
        ),
    ]
)

FULL_MDA = MULTIPOINT_MDA.replace(z_plan={"range": 0.2, "step": 0.1})

PLATE_MDA = useq.MDASequence(
    axis_order="pzc",
    channels=["Cy5", "FITC"],
    stage_positions=useq.WellPlatePlan(
        plate=useq.WellPlate.from_str("96-well"),
        a1_center_xy=(0, 0),
        selected_wells=((0, 1), (0, 1)),
        well_points_plan=useq.GridRowsColumns(rows=1, columns=2),
    ),
)

MDA_SEQUENCES = [
    pytest.param(SIMPLE_MDA, id="simple"),
    pytest.param(MULTIPOINT_MDA, id="multipoint"),
    pytest.param(GRID_MDA, id="grid"),
    pytest.param(GRID_MDA_SUBSEQUENCE, id="grid_subsequence"),
    pytest.param(PLATE_MDA, id="plate"),
    pytest.param(FULL_MDA, id="full"),
]


# -----------------------------------------------------------------------------
# Test: OMEWriterHandler with zarr and tiff backends
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_handler_zarr(mda: useq.MDASequence, tmp_path: Path, core: CMMCorePlus) -> None:
    """Test OMEWriterHandler writing to OME-ZARR."""
    handler = OMEWriterHandler(
        tmp_path / "test.ome.zarr", backend="tensorstore", overwrite=True
    )
    core.mda.run(mda, output=handler)

    assert (tmp_path / "test.ome.zarr").exists()
    assert handler.stream is None  # closed after sequence finishes


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_handler_tiff(mda: useq.MDASequence, tmp_path: Path, core: CMMCorePlus) -> None:
    """Test OMEWriterHandler writing to OME-TIFF."""
    handler = OMEWriterHandler(
        tmp_path / "test.ome.tiff", backend="tifffile", overwrite=True
    )
    core.mda.run(mda, output=handler)

    tiff_files = list(tmp_path.glob("*.ome.tiff")) + list(tmp_path.glob("*.ome.tif"))
    assert len(tiff_files) >= 1


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_handler_auto_backend(
    mda: useq.MDASequence, tmp_path: Path, core: CMMCorePlus
) -> None:
    """Test backend='auto' infers format from path extension."""
    zarr_path = tmp_path / "auto_test.ome.zarr"
    handler = OMEWriterHandler(zarr_path, backend="auto")
    core.mda.run(mda, output=handler)
    assert zarr_path.exists()


# -----------------------------------------------------------------------------
# Test: OMEWriterHandler.in_tmpdir
# -----------------------------------------------------------------------------


def test_in_tmpdir(core: CMMCorePlus) -> None:
    """Test OMEWriterHandler.in_tmpdir creates temp directory."""
    handler = OMEWriterHandler.in_tmpdir()
    core.mda.run(SIMPLE_MDA, output=handler)

    assert "_pmmcp_tmp_" in handler.path
    assert handler.path.endswith(".ome.zarr")
    assert handler._overwrite is True


def test_in_tmpdir_tiff_backend(core: CMMCorePlus) -> None:
    """Test in_tmpdir with tifffile backend infers .ome.tiff suffix."""
    handler = OMEWriterHandler.in_tmpdir(backend="tifffile")
    core.mda.run(SIMPLE_MDA, output=handler)

    assert handler.path.endswith(".ome.tiff")


def test_in_tmpdir_custom_suffix_and_prefix(core: CMMCorePlus) -> None:
    """Test OMEWriterHandler.in_tmpdir with custom suffix and prefix."""
    handler = OMEWriterHandler.in_tmpdir(suffix=".zarr", prefix="custom_")
    core.mda.run(SIMPLE_MDA, output=handler)

    assert "custom_" in handler.path
    assert handler.path.endswith(".zarr")


def test_in_tmpdir_custom_dir(tmp_path: Path, core: CMMCorePlus) -> None:
    """Test in_tmpdir with custom directory."""
    handler = OMEWriterHandler.in_tmpdir(dir=tmp_path)
    core.mda.run(SIMPLE_MDA, output=handler)

    assert str(tmp_path) in handler.path


def test_in_tmpdir_suffix_backend_mismatch() -> None:
    """Test that mismatched suffix and backend in in_tmpdir raises error."""
    with pytest.raises(ValueError, match="cannot be used with ZARR path"):
        OMEWriterHandler.in_tmpdir(backend="tifffile", suffix=".zarr")

    with pytest.raises(ValueError, match="cannot be used with TIFF path"):
        OMEWriterHandler.in_tmpdir(backend="tensorstore", suffix=".tiff")


# -----------------------------------------------------------------------------
# Test: Validation
# -----------------------------------------------------------------------------


def test_backend_path_mismatch() -> None:
    """Test that mismatched backend and path extension raises error."""
    with pytest.raises(ValueError, match="cannot be used with ZARR path"):
        OMEWriterHandler("test.zarr", backend="tifffile")

    with pytest.raises(ValueError, match="cannot be used with TIFF path"):
        OMEWriterHandler("test.ome.tiff", backend="tensorstore")


def test_all_zarr_backends_validated(tmp_path: Path) -> None:
    """Test all ZARR backend names are validated correctly."""
    zarr_backends = ["tensorstore", "acquire-zarr", "zarr-python", "zarrs-python"]

    for backend in zarr_backends:
        # Should work with .zarr extension
        handler = OMEWriterHandler(tmp_path / f"test_{backend}.zarr", backend=backend)  # type: ignore[arg-type]
        assert handler is not None

        # Should fail with .tiff extension
        with pytest.raises(ValueError, match="cannot be used with TIFF path"):
            OMEWriterHandler(tmp_path / f"test_{backend}.tiff", backend=backend)  # type: ignore[arg-type]


def test_auto_backend_no_validation_error(tmp_path: Path) -> None:
    """Test that backend='auto' doesn't trigger validation errors."""
    handler_zarr = OMEWriterHandler(tmp_path / "test.zarr", backend="auto")
    assert handler_zarr is not None

    handler_tiff = OMEWriterHandler(tmp_path / "test.tiff", backend="auto")
    assert handler_tiff is not None


def test_case_insensitive_extension(tmp_path: Path) -> None:
    """Test that extension matching is case-insensitive."""
    OMEWriterHandler(tmp_path / "test.ZARR", backend="tensorstore")
    OMEWriterHandler(tmp_path / "test.TIFF", backend="tifffile")

    with pytest.raises(ValueError, match="cannot be used with ZARR path"):
        OMEWriterHandler(tmp_path / "test.ZARR", backend="tifffile")


def test_empty_and_whitespace_path_raises_error() -> None:
    """Test that empty or whitespace-only path raises ValueError."""
    with pytest.raises(ValueError, match="`path` is required"):
        OMEWriterHandler("")

    with pytest.raises(ValueError, match="`path` is required"):
        OMEWriterHandler("   ")

    with pytest.raises(ValueError, match="`path` is required"):
        OMEWriterHandler("\t\n")


# -----------------------------------------------------------------------------
# Test: Handler lifecycle and stream management
# -----------------------------------------------------------------------------


def test_stream_lifecycle(tmp_path: Path, core: CMMCorePlus) -> None:
    """Test that stream is None before and after a sequence run."""
    handler = OMEWriterHandler(tmp_path / "test.zarr", backend="tensorstore")

    assert handler.stream is None

    core.mda.run(SIMPLE_MDA, output=handler)

    assert handler.stream is None


def test_handler_reuse(tmp_path: Path, core: CMMCorePlus) -> None:
    """Test that handler can be reused for multiple sequences."""
    handler = OMEWriterHandler(
        tmp_path / "test.zarr", backend="tensorstore", overwrite=True
    )

    core.mda.run(SIMPLE_MDA, output=handler)
    assert handler.stream is None

    core.mda.run(SIMPLE_MDA, output=handler)
    assert handler.stream is None


# -----------------------------------------------------------------------------
# Test: Optional zarr backends (smoke tests, run only if installed)
# -----------------------------------------------------------------------------

_have_acquire_zarr = importlib.util.find_spec("acquire_zarr") is not None
_have_zarr = importlib.util.find_spec("zarr") is not None
_have_zarrs = _have_zarr and importlib.util.find_spec("zarrs") is not None

OPTIONAL_ZARR_BACKENDS = [
    pytest.param(
        "acquire-zarr",
        marks=pytest.mark.skipif(
            not _have_acquire_zarr, reason="acquire-zarr not installed"
        ),
        id="acquire-zarr",
    ),
    pytest.param(
        "zarr-python",
        marks=pytest.mark.skipif(not _have_zarr, reason="zarr not installed"),
        id="zarr-python",
    ),
    pytest.param(
        "zarrs-python",
        marks=pytest.mark.skipif(not _have_zarrs, reason="zarrs not installed"),
        id="zarrs-python",
    ),
]


@pytest.mark.parametrize("backend", OPTIONAL_ZARR_BACKENDS)
def test_optional_zarr_backend(backend: str, tmp_path: Path, core: CMMCorePlus) -> None:
    """Smoke test: optional zarr backends can write a simple MDA."""
    handler = OMEWriterHandler(
        tmp_path / "test.ome.zarr",
        backend=backend,
        overwrite=True,  # type: ignore[arg-type]
    )
    core.mda.run(SIMPLE_MDA, output=handler)
    assert (tmp_path / "test.ome.zarr").exists()
