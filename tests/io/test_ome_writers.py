"""Tests for OMEWriterHandler with various output argument combinations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import useq

from pymmcore_plus.mda import Output
from pymmcore_plus.mda.handlers import OMEWriterHandler

if TYPE_CHECKING:
    from pathlib import Path

    from pymmcore_plus import CMMCorePlus

# Skip all tests if ome-writers is not installed
omew = pytest.importorskip("ome_writers")

# -----------------------------------------------------------------------------
# MDA Sequences - same patterns as test_zarr_writers.py
# -----------------------------------------------------------------------------

SIMPLE_MDA = useq.MDASequence(
    channels=["Cy5", "FITC"],
    time_plan={"interval": 0.1, "loops": 2},
    axis_order="tpcz",
)

MULTIPOINT_MDA = SIMPLE_MDA.replace(
    channels=["Cy5", "FITC"],
    stage_positions=[(222, 1, 1), (111, 0, 0)],
    time_plan={"interval": 0.1, "loops": 2},
)

GRID_MDA = SIMPLE_MDA.replace(
    grid_plan={"rows": 2, "columns": 2, "mode": "row_wise_snake"},
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

# Note: COMPLEX_MDA with ragged dimensions (positions with different z-plans)
# is not supported by ome-writers, so we exclude it from these tests.

MDA_SEQUENCES = [
    pytest.param(SIMPLE_MDA, id="simple"),
    pytest.param(MULTIPOINT_MDA, id="multipoint"),
    pytest.param(GRID_MDA, id="grid"),
    pytest.param(FULL_MDA, id="full"),
    pytest.param(PLATE_MDA, id="plate"),
]


# -----------------------------------------------------------------------------
# Test: Output object with zarr path and format
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_output_object_zarr(
    mda: useq.MDASequence, tmp_path: Path, core: CMMCorePlus
) -> None:
    """Test Output object with zarr path and explicit format."""
    out = Output(path=tmp_path / "test.ome.zarr", format="tensorstore")
    core.mda.run(mda, output=out)

    # Verify output was created
    assert (tmp_path / "test.ome.zarr").exists()


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_output_object_tiff(
    mda: useq.MDASequence, tmp_path: Path, core: CMMCorePlus
) -> None:
    """Test Output object with tiff path and explicit format."""
    out = Output(path=tmp_path / "test.ome.tiff", format="tifffile")
    core.mda.run(mda, output=out)

    # TIFF files may be split by position
    tiff_files = list(tmp_path.glob("*.ome.tiff")) + list(tmp_path.glob("*.ome.tif"))
    assert len(tiff_files) >= 1


# -----------------------------------------------------------------------------
# Test: String path (format auto-detected from extension)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_string_path_zarr(
    mda: useq.MDASequence, tmp_path: Path, core: CMMCorePlus
) -> None:
    """Test string path with .zarr extension (auto-detect format)."""
    path = str(tmp_path / "test.ome.zarr")
    core.mda.run(mda, output=path)

    assert (tmp_path / "test.ome.zarr").exists()


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_string_path_tiff(
    mda: useq.MDASequence, tmp_path: Path, core: CMMCorePlus
) -> None:
    """Test string path with .tiff extension (auto-detect format)."""
    path = str(tmp_path / "test.ome.tiff")
    core.mda.run(mda, output=path)

    tiff_files = list(tmp_path.glob("*.ome.tiff")) + list(tmp_path.glob("*.ome.tif"))
    assert len(tiff_files) >= 1


# -----------------------------------------------------------------------------
# Test: Path object (format auto-detected from extension)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_path_object_zarr(
    mda: useq.MDASequence, tmp_path: Path, core: CMMCorePlus
) -> None:
    """Test Path object with .zarr extension (auto-detect format)."""
    path = tmp_path / "test.ome.zarr"
    core.mda.run(mda, output=path)

    assert path.exists()


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_path_object_tiff(
    mda: useq.MDASequence, tmp_path: Path, core: CMMCorePlus
) -> None:
    """Test Path object with .tiff extension (auto-detect format)."""
    path = tmp_path / "test.ome.tiff"
    core.mda.run(mda, output=path)

    tiff_files = list(tmp_path.glob("*.ome.tiff")) + list(tmp_path.glob("*.ome.tif"))
    assert len(tiff_files) >= 1


# -----------------------------------------------------------------------------
# Test: Tuple of (path, format)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_tuple_path_format_zarr(
    mda: useq.MDASequence, tmp_path: Path, core: CMMCorePlus
) -> None:
    """Test tuple of (path, format) for zarr."""
    path = str(tmp_path / "test.ome.zarr")
    core.mda.run(mda, output=(path, "tensorstore"))

    assert (tmp_path / "test.ome.zarr").exists()


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_tuple_path_format_tiff(
    mda: useq.MDASequence, tmp_path: Path, core: CMMCorePlus
) -> None:
    """Test tuple of (path, format) for tiff."""
    path = str(tmp_path / "test.ome.tiff")
    core.mda.run(mda, output=(path, "tifffile"))

    tiff_files = list(tmp_path.glob("*.ome.tiff")) + list(tmp_path.glob("*.ome.tif"))
    assert len(tiff_files) >= 1


# -----------------------------------------------------------------------------
# Test: Handler object directly
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_handler_object_zarr(
    mda: useq.MDASequence, tmp_path: Path, core: CMMCorePlus
) -> None:
    """Test passing OMEWriterHandler directly for zarr."""
    handler = OMEWriterHandler(
        tmp_path / "test.ome.zarr", backend="tensorstore", overwrite=True
    )
    core.mda.run(mda, output=handler)

    assert (tmp_path / "test.ome.zarr").exists()
    assert handler.stream is None  # closed after sequence finishes


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_handler_object_tiff(
    mda: useq.MDASequence, tmp_path: Path, core: CMMCorePlus
) -> None:
    """Test passing OMEWriterHandler directly for tiff."""
    handler = OMEWriterHandler(
        tmp_path / "test.ome.tiff", backend="tifffile", overwrite=True
    )
    core.mda.run(mda, output=handler)

    tiff_files = list(tmp_path.glob("*.ome.tiff")) + list(tmp_path.glob("*.ome.tif"))
    assert len(tiff_files) >= 1


# -----------------------------------------------------------------------------
# Test: List of outputs for multiple outputs
# -----------------------------------------------------------------------------


def test_list_of_outputs(tmp_path: Path, core: CMMCorePlus) -> None:
    """Test list of multiple Output objects."""
    out1 = Output(path=tmp_path / "test1.ome.zarr", format="tensorstore")
    out2 = Output(path=tmp_path / "test2.ome.zarr", format="tensorstore")

    core.mda.run(SIMPLE_MDA, output=[out1, out2])

    assert (tmp_path / "test1.ome.zarr").exists()
    assert (tmp_path / "test2.ome.zarr").exists()


def test_list_of_paths(tmp_path: Path, core: CMMCorePlus) -> None:
    """Test list of string paths."""
    path1 = str(tmp_path / "test1.ome.zarr")
    path2 = str(tmp_path / "test2.ome.zarr")

    core.mda.run(SIMPLE_MDA, output=[path1, path2])

    assert (tmp_path / "test1.ome.zarr").exists()
    assert (tmp_path / "test2.ome.zarr").exists()


def test_list_of_handlers(tmp_path: Path, core: CMMCorePlus) -> None:
    """Test list of handler objects."""
    handler1 = OMEWriterHandler(
        tmp_path / "test1.ome.zarr", backend="tensorstore", overwrite=True
    )
    handler2 = OMEWriterHandler(
        tmp_path / "test2.ome.zarr", backend="tensorstore", overwrite=True
    )

    core.mda.run(SIMPLE_MDA, output=[handler1, handler2])

    assert (tmp_path / "test1.ome.zarr").exists()
    assert (tmp_path / "test2.ome.zarr").exists()


def test_mixed_list_of_outputs(tmp_path: Path, core: CMMCorePlus) -> None:
    """Test list with mixed output types."""
    out1 = Output(path=tmp_path / "test1.ome.zarr", format="tensorstore")
    path2 = str(tmp_path / "test2.ome.zarr")
    handler3 = OMEWriterHandler(
        tmp_path / "test3.ome.zarr", backend="tensorstore", overwrite=True
    )

    core.mda.run(SIMPLE_MDA, output=[out1, path2, handler3])

    assert (tmp_path / "test1.ome.zarr").exists()
    assert (tmp_path / "test2.ome.zarr").exists()
    assert (tmp_path / "test3.ome.zarr").exists()


# -----------------------------------------------------------------------------
# Test: memory:// backward compatibility (uses TensorStoreHandler)
# -----------------------------------------------------------------------------


def test_memory_output_uses_tensorstore(core: CMMCorePlus) -> None:
    """Test memory:// uses TensorStoreHandler for backward compatibility."""
    from pymmcore_plus.mda.handlers import TensorStoreHandler, handler_for_output

    out = Output(path="memory://", format="tensorstore")
    handler = handler_for_output(out)

    # Should return TensorStoreHandler, not OMEWriterHandler
    assert isinstance(handler, TensorStoreHandler)

    core.mda.run(SIMPLE_MDA, output=handler)


def test_empty_path_raises_error() -> None:
    """Test that empty path raises ValueError."""
    # OMEWriterHandler with empty path
    with pytest.raises(ValueError, match="path is required"):
        OMEWriterHandler("")

    # Output with empty path
    with pytest.raises(ValueError, match="`path` argument is required for Output"):
        Output("")


# -----------------------------------------------------------------------------
# Test: OMEWriterHandler.in_tmpdir
# -----------------------------------------------------------------------------


def test_in_tmpdir(core: CMMCorePlus) -> None:
    """Test OMEWriterHandler.in_tmpdir creates temp directory."""
    handler = OMEWriterHandler.in_tmpdir()
    core.mda.run(SIMPLE_MDA, output=handler)

    assert "_pmmcp_tmp_" in handler.path
    assert handler.path.endswith(".ome.zarr")


def test_in_tmpdir_custom_suffix(core: CMMCorePlus) -> None:
    """Test OMEWriterHandler.in_tmpdir with custom suffix."""
    handler = OMEWriterHandler.in_tmpdir(suffix=".zarr", prefix="custom_")
    core.mda.run(SIMPLE_MDA, output=handler)

    assert "custom_" in handler.path
    assert handler.path.endswith(".zarr")


# -----------------------------------------------------------------------------
# Test: OMEWriterHandler.from_output
# -----------------------------------------------------------------------------


def test_from_output_with_path(tmp_path: Path, core: CMMCorePlus) -> None:
    """Test OMEWriterHandler.from_output with path."""
    out = Output(path=tmp_path / "test.ome.zarr", format="tensorstore")
    handler = OMEWriterHandler.from_output(out, overwrite=True)

    core.mda.run(SIMPLE_MDA, output=handler)

    assert (tmp_path / "test.ome.zarr").exists()


def test_from_output_adds_extension(tmp_path: Path, core: CMMCorePlus) -> None:
    """Test that from_output adds extension based on backend."""
    # Path without extension + zarr backend -> adds .ome.zarr
    out = Output(path=tmp_path / "test_no_ext", format="tensorstore")
    handler = OMEWriterHandler.from_output(out, overwrite=True)
    assert handler.path.endswith(".ome.zarr")

    # Path without extension + tiff backend -> adds .ome.tiff
    out = Output(path=tmp_path / "test_no_ext2", format="tifffile")
    handler = OMEWriterHandler.from_output(out, overwrite=True)
    assert handler.path.endswith(".ome.tiff")


# -----------------------------------------------------------------------------
# Test: ome-writers Format objects (OmeTiffFormat, OmeZarrFormat)
# -----------------------------------------------------------------------------


def test_output_with_ome_zarr_format(tmp_path: Path, core: CMMCorePlus) -> None:
    """Test Output with ome-writers OmeZarrFormat object."""
    ome_format = omew.OmeZarrFormat(backend="tensorstore")
    out = Output(path=tmp_path / "test.ome.zarr", format=ome_format)

    core.mda.run(SIMPLE_MDA, output=out)

    assert (tmp_path / "test.ome.zarr").exists()


def test_output_with_ome_tiff_format(tmp_path: Path, core: CMMCorePlus) -> None:
    """Test Output with ome-writers OmeTiffFormat object."""
    ome_format = omew.OmeTiffFormat()
    out = Output(path=tmp_path / "test.ome.tiff", format=ome_format)

    core.mda.run(SIMPLE_MDA, output=out)

    tiff_files = list(tmp_path.glob("*.ome.tiff")) + list(tmp_path.glob("*.ome.tif"))
    assert len(tiff_files) >= 1


# -----------------------------------------------------------------------------
# Test: Validation
# -----------------------------------------------------------------------------


def test_backend_path_mismatch_zarr_tiff() -> None:
    """Test that mismatched backend and path raises error."""
    with pytest.raises(ValueError, match="cannot be used with zarr path"):
        OMEWriterHandler("test.zarr", backend="tifffile")


def test_backend_path_mismatch_tiff_zarr() -> None:
    """Test that mismatched backend and path raises error."""
    with pytest.raises(ValueError, match="cannot be used with TIFF path"):
        OMEWriterHandler("test.ome.tiff", backend="tensorstore")


# -----------------------------------------------------------------------------
# Test: No output (None) should not create any handlers
# -----------------------------------------------------------------------------


def test_no_output(tmp_path: Path, core: CMMCorePlus) -> None:
    """Test that output=None doesn't create any files."""
    core.mda.run(SIMPLE_MDA, output=None)

    # No zarr or tiff files should be created
    zarr_files = list(tmp_path.glob("*.zarr"))
    tiff_files = list(tmp_path.glob("*.tiff")) + list(tmp_path.glob("*.tif"))
    assert len(zarr_files) == 0
    assert len(tiff_files) == 0


def test_default_output(tmp_path: Path, core: CMMCorePlus) -> None:
    """Test that default output (no argument) doesn't create files."""
    core.mda.run(SIMPLE_MDA)

    # No zarr or tiff files should be created
    zarr_files = list(tmp_path.glob("*.zarr"))
    tiff_files = list(tmp_path.glob("*.tiff")) + list(tmp_path.glob("*.tif"))
    assert len(zarr_files) == 0
    assert len(tiff_files) == 0
