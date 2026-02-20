from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import useq

from pymmcore_plus.mda.handlers import (
    ImageSequenceWriter,
    OMERunnerHandler,
    OMEZarrWriter,
    StreamSettings,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pymmcore_plus import CMMCorePlus

ome_writers = pytest.importorskip("ome_writers")


# ------------------- fixtures -------------------


@pytest.fixture
def zarr_settings(tmp_path: Path) -> StreamSettings:
    return StreamSettings(
        root_path=str(tmp_path / "test.ome.zarr"),
        overwrite=True,
    )


@pytest.fixture
def tiff_settings(tmp_path: Path) -> StreamSettings:
    return StreamSettings(
        root_path=str(tmp_path / "test.ome.tiff"),
        overwrite=True,
    )


SIMPLE_MDA = useq.MDASequence(
    channels=["Cy5", "FITC"],
    time_plan={"interval": 0.1, "loops": 2},
    axis_order="tpcz",
)

MULTIPOINT_MDA = useq.MDASequence(
    channels=["Cy5"],
    stage_positions=[(222, 1, 1), (111, 0, 0)],
    time_plan={"interval": 0.1, "loops": 2},
    axis_order="tpcz",
)

SUBSEQUENCE_GRID_MDA = useq.MDASequence(
    channels=["Cy5"],
    stage_positions=[
        (222, 1, 1),
        useq.Position(
            x=111,
            y=0,
            z=0,
            sequence=useq.MDASequence(
                grid_plan=useq.GridRowsColumns(rows=2, columns=2)
            ),
        ),
    ],
    time_plan={"interval": 0.1, "loops": 2},
    axis_order="tpgcz",
)


# ------------------- StreamSettings -------------------


def test_stream_settings_defaults(tmp_path: Path) -> None:
    s = StreamSettings(root_path=str(tmp_path / "out.ome.zarr"))
    assert s.format == "auto"
    assert s.overwrite is False
    assert s.dimensions is None
    assert s.dtype is None
    assert s.plate is None


def test_stream_settings_deprecated_asynchronous(tmp_path: Path) -> None:
    with pytest.warns(DeprecationWarning, match="asynchronous is deprecated"):
        StreamSettings(
            root_path=str(tmp_path / "out.ome.zarr"),
            asynchronous=False,
        )


def test_stream_settings_deprecated_queue_maxsize(tmp_path: Path) -> None:
    with pytest.warns(DeprecationWarning, match="queue_maxsize is deprecated"):
        StreamSettings(
            root_path=str(tmp_path / "out.ome.zarr"),
            queue_maxsize=50,
        )


# ------------------- OMERunnerHandler -------------------


def test_handler_requires_root_path() -> None:
    settings = StreamSettings(root_path="test.ome.zarr", overwrite=True)
    object.__setattr__(settings, "root_path", "")
    with pytest.raises(ValueError, match="`path` is always required"):
        OMERunnerHandler(settings)


def test_handler_properties(zarr_settings: StreamSettings) -> None:
    handler = OMERunnerHandler(zarr_settings)
    assert handler.stream is None
    assert handler.stream_settings is zarr_settings


def test_handler_in_tempdir() -> None:
    handler = OMERunnerHandler.in_tempdir()
    assert handler.stream_settings.root_path
    assert "pymmcp_runner_" in str(handler.stream_settings.root_path)
    assert handler.stream_settings.format == "tensorstore"


def test_handler_in_tempdir_with_settings() -> None:
    settings = StreamSettings(root_path="sub.ome.zarr", overwrite=True)
    handler = OMERunnerHandler.in_tempdir(stream_settings=settings)
    assert handler.stream_settings.root_path
    assert handler.stream_settings.root_path.endswith("sub.ome.zarr")
    assert handler.stream_settings.overwrite is True


def test_handler_cleanup_without_prepare(zarr_settings: StreamSettings) -> None:
    handler = OMERunnerHandler(zarr_settings)
    handler.cleanup()  # should not raise
    assert handler.stream is None


@pytest.mark.parametrize(
    "meta, match",
    [
        (None, "meta is required"),
        ({"image_infos": []}, "image_infos"),
        ({"image_infos": [{"dtype": "uint16"}]}, "width.*height"),
        ({"image_infos": [{"width": 512, "height": 512}]}, "dtype"),
    ],
    ids=["no-meta", "empty-image-infos", "missing-dims", "missing-dtype"],
)
def test_handler_prepare_validation(
    zarr_settings: StreamSettings, meta: dict | None, match: str
) -> None:
    handler = OMERunnerHandler(zarr_settings)
    with pytest.raises(ValueError, match=match):
        handler.prepare(SIMPLE_MDA, meta)  # type: ignore[arg-type]


# ------------------- integration with core.mda.run -------------------

MDA_SEQUENCES = [
    pytest.param(SIMPLE_MDA, id="simple"),
    pytest.param(MULTIPOINT_MDA, id="multipoint"),
    pytest.param(SUBSEQUENCE_GRID_MDA, id="subsequence-grid"),
]


# --- runner handler (BaseRunnerHandler) output ---


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
@pytest.mark.parametrize("ext", [".ome.zarr", ".ome.tiff"], ids=["zarr", "tiff"])
def test_run_with_ome_runner_handler(
    tmp_path: Path, core: CMMCorePlus, mda: useq.MDASequence, ext: str
) -> None:
    """output=OMERunnerHandler(StreamSettings(root_path=...))"""
    settings = StreamSettings(root_path=str(tmp_path / f"out{ext}"), overwrite=True)
    handler = OMERunnerHandler(settings)
    core.mda.run(mda, output=handler)
    assert handler.stream is None


# --- string path output (resolved via handler_for_path) ---


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
@pytest.mark.parametrize("ext", [".ome.zarr", ".ome.tiff"], ids=["zarr", "tiff"])
def test_run_via_path(
    tmp_path: Path, core: CMMCorePlus, mda: useq.MDASequence, ext: str
) -> None:
    """output="example.ome.zarr" / output="example.ome.tiff" """
    core.mda.run(mda, output=str(tmp_path / f"via_path{ext}"))


def test_run_via_directory_path(tmp_path: Path, core: CMMCorePlus) -> None:
    """output="example_tiff_sequence" (directory → ImageSequenceWriter)"""
    core.mda.run(SIMPLE_MDA, output=str(tmp_path / "tiff_seq"))
    assert (tmp_path / "tiff_seq").is_dir()


# --- signal-based handler output (SupportsFrameReady) ---


def test_run_with_ome_zarr_writer(tmp_path: Path, core: CMMCorePlus) -> None:
    """output=OMEZarrWriter("example.ome.zarr")"""
    pytest.importorskip("zarr")
    writer = OMEZarrWriter(tmp_path / "out.ome.zarr")
    core.mda.run(SIMPLE_MDA, output=writer)


def _make_ome_tiff_writer(tmp_path: Path) -> Any:
    """Import OMETiffWriter only if tifffile is available."""
    from pymmcore_plus.mda.handlers import OMETiffWriter

    return OMETiffWriter(tmp_path / "out.ome.tiff")


def test_run_with_ome_tiff_writer(tmp_path: Path, core: CMMCorePlus) -> None:
    """output=OMETiffWriter("example.ome.tiff")"""
    pytest.importorskip("tifffile")
    writer = _make_ome_tiff_writer(tmp_path)
    core.mda.run(SIMPLE_MDA, output=writer)


def test_run_with_tensorstore_handler(tmp_path: Path, core: CMMCorePlus) -> None:
    """output=TensorStoreHandler(path="example.ome.zarr")"""
    ts = pytest.importorskip("tensorstore")  # noqa: F841
    from pymmcore_plus.mda.handlers import TensorStoreHandler

    writer = TensorStoreHandler(path=tmp_path / "out.ome.zarr")
    core.mda.run(SIMPLE_MDA, output=writer)


def test_run_with_image_sequence_writer(tmp_path: Path, core: CMMCorePlus) -> None:
    """output=ImageSequenceWriter("example_sequence", extension=".tiff")"""
    writer = ImageSequenceWriter(tmp_path / "seq_out", extension=".tiff")
    core.mda.run(SIMPLE_MDA, output=writer)
    assert (tmp_path / "seq_out").is_dir()


# --- multiple outputs / list ---


def test_run_via_path_list(tmp_path: Path, core: CMMCorePlus) -> None:
    """output=["example.ome.zarr", "example.ome.tiff"]"""
    core.mda.run(
        SIMPLE_MDA,
        output=[
            str(tmp_path / "example.ome.zarr"),
            str(tmp_path / "example.ome.tiff"),
        ],
    )


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_run_multiple_handlers(
    tmp_path: Path, core: CMMCorePlus, mda: useq.MDASequence
) -> None:
    h_zarr = OMERunnerHandler(
        StreamSettings(root_path=str(tmp_path / "multi.ome.zarr"), overwrite=True)
    )
    h_tiff = OMERunnerHandler(
        StreamSettings(root_path=str(tmp_path / "multi.ome.tiff"), overwrite=True)
    )
    core.mda.run(mda, output=[h_zarr, h_tiff])
    assert h_zarr.stream is None
    assert h_tiff.stream is None


# --- edge cases ---


def test_run_no_output(core: CMMCorePlus) -> None:
    core.mda.run(SIMPLE_MDA, output=None)


def test_run_invalid_path(core: CMMCorePlus) -> None:
    with pytest.raises(ValueError, match="Could not infer"):
        core.mda.run(SIMPLE_MDA, output="/some/path.xyz")


def test_run_invalid_handler(core: CMMCorePlus) -> None:
    with pytest.raises(TypeError, match="callable frameReady"):
        core.mda.run(SIMPLE_MDA, output=object())  # type: ignore[arg-type]


def test_get_output_handlers_empty(core: CMMCorePlus) -> None:
    assert not core.mda.get_output_handlers()
