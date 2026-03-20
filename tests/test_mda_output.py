"""Tests for MDA runner output/sink integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
import useq
from ome_writers import AcquisitionSettings, Dimension
from pymmcore_plus.mda._runner import (
    MDARunner,
    _OmeWritersSink,
    _merge_user_dim_overrides,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from pymmcore_plus import CMMCorePlus


# --- _OmeWritersSink unit tests ---


@pytest.fixture
def zarr_sink(tmp_path: Path) -> _OmeWritersSink:
    return _OmeWritersSink.from_output(tmp_path / "out.ome.zarr")


def test_from_output_path(tmp_path: Path) -> None:
    dest = tmp_path / "out.ome.zarr"
    sink = _OmeWritersSink.from_output(dest)
    assert sink._settings.root_path == str(dest)


def test_from_output_scratch() -> None:
    sink = _OmeWritersSink.from_output("scratch")
    assert sink._settings.format.name == "scratch"
    sink = _OmeWritersSink.from_output("memory")
    assert sink._settings.format.name == "scratch"


def test_from_output_acquisition_settings() -> None:
    settings = AcquisitionSettings(root_path="/tmp/test.ome.zarr")
    sink = _OmeWritersSink.from_output(settings)
    assert sink._settings == settings


def test_sink_get_close_before_setup(zarr_sink: _OmeWritersSink) -> None:
    assert zarr_sink.get_view() is None
    zarr_sink.close()  # should not raise


def test_sink_skip_delegates_to_stream() -> None:
    sink = _OmeWritersSink(AcquisitionSettings(root_path="/tmp/x.ome.zarr"))
    mock_stream = Mock()
    sink._stream = mock_stream
    sink.skip(frames=3)
    mock_stream.skip.assert_called_once_with(frames=3)


# --- MDARunner integration tests ---


def test_get_view_no_sink() -> None:
    assert MDARunner().get_view() is None


def test_run_with_zarr_output(core: CMMCorePlus, tmp_path: Path) -> None:
    runner = core.mda
    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=2))

    out = tmp_path / "test.ome.zarr"
    runner.run(seq, output=out)
    view = runner.get_view()
    assert view is not None
    assert view.shape[:-2] == (2,)
    assert out.exists()


def test_run_with_tiff_output(core: CMMCorePlus, tmp_path: Path) -> None:
    runner = core.mda
    out = tmp_path / "test.ome.tiff"
    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=2))
    runner.run(seq, output=out)
    assert out.exists()


def test_run_with_acquisition_settings(core: CMMCorePlus, tmp_path: Path) -> None:
    runner = core.mda
    dest = tmp_path / "out.ome.zarr"
    settings = AcquisitionSettings(root_path=str(dest), overwrite=True)
    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=2))
    runner.run(seq, output=settings)
    assert dest.exists()


def test_coerce_outputs_rejects_multiple_sinks() -> None:
    runner = MDARunner()
    with pytest.raises(NotImplementedError, match="Only one"):
        runner._coerce_outputs(["/a.ome.zarr", "/b.ome.zarr"])


def test_coerce_outputs_rejects_bad_handler() -> None:
    runner = MDARunner()
    with pytest.raises(TypeError, match="frameReady"):
        runner._coerce_outputs([object()])  # type: ignore[list-item]


def test_run_with_custom_handler_and_path(core: CMMCorePlus, tmp_path: Path) -> None:
    runner = core.mda
    out = tmp_path / "test.ome.zarr"

    handler = Mock()
    handler.frameReady = Mock()

    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=2))
    runner.run(seq, output=[out, handler])

    assert handler.frameReady.call_count == 2
    assert out.exists()


@pytest.mark.parametrize("fmt", ["scratch", "ome-zarr", "ome-tiff"])
def test_run_with_ragged_sequence(core: CMMCorePlus, tmp_path: Path, fmt: str) -> None:
    """Ragged sequences (unsupported by ome-writers) fall back to unbounded 3D."""
    # do_stack=False on one channel with a z_plan creates a ragged dimension
    seq = useq.MDASequence(
        channels=[
            {"config": "DAPI", "exposure": 1},
            {"config": "FITC", "exposure": 1, "do_stack": False},
        ],
        z_plan={"range": 3, "step": 1},
    )

    out = AcquisitionSettings(root_path=str(tmp_path / "test"), format=fmt)

    core.mda.run(seq, output=out)
    view = core.mda.get_view()
    assert view is not None
    # unbounded 3D fallback: each event becomes one "time" frame
    assert view.shape[:-2] == (5,)  # (4 planes for one channel + 1 for the other)


def test_run_with_event_iterator(core: CMMCorePlus) -> None:
    """A plain iterator of MDAEvents (non-deterministic) saves data."""
    from useq import MDAEvent

    def event_generator() -> Iterator[MDAEvent]:
        for i in range(3):
            yield MDAEvent(metadata={"frame": i})

    core.mda.run(event_generator(), output="scratch")

    view = core.mda.get_view()
    assert view is not None
    assert view.shape[:-2] == (3,)


# --- _merge_user_dim_overrides tests ---


def test_merge_applies_overridable_fields() -> None:
    """User chunk_size, shard_size_chunks, unit, scale, translation are merged."""
    useq_dims = [
        Dimension(name="t", count=10, type="time", unit="second", scale=1.0),
        Dimension(name="y", count=512, type="space", unit="micrometer"),
        Dimension(name="x", count=512, type="space", unit="micrometer"),
    ]
    overrides = {
        "t": Dimension(name="t", chunk_size=1, scale=2.0),
        "y": Dimension(name="y", chunk_size=256, shard_size_chunks=4),
    }
    merged = _merge_user_dim_overrides(useq_dims, overrides)

    assert merged[0].chunk_size == 1
    assert merged[0].scale == 2.0
    assert merged[0].count == 10  # not overridden
    assert merged[0].unit == "second"  # not overridden (user had None)
    assert merged[1].chunk_size == 256
    assert merged[1].shard_size_chunks == 4
    assert merged[2].chunk_size is None  # no override for x


def test_merge_warns_on_count_mismatch(caplog: pytest.LogCaptureFixture) -> None:
    """Warning emitted when user count differs from sequence-derived count."""
    useq_dims = [
        Dimension(name="t", count=50, type="time"),
        Dimension(name="y", count=512, type="space"),
        Dimension(name="x", count=512, type="space"),
    ]
    overrides = {
        "t": Dimension(name="t", count=100, type="time"),
    }
    with caplog.at_level(logging.WARNING, logger="pymmcore-plus"):
        _merge_user_dim_overrides(useq_dims, overrides)

    assert "count=100" in caplog.text
    assert "50" in caplog.text
    # count should NOT be overridden
    assert useq_dims[0].count == 50


def test_merge_no_warning_when_values_match() -> None:
    """No warning when user-provided count matches sequence-derived count."""
    useq_dims = [
        Dimension(name="t", count=50, type="time"),
        Dimension(name="y", count=512, type="space"),
        Dimension(name="x", count=512, type="space"),
    ]
    overrides = {
        "t": Dimension(name="t", count=50, chunk_size=1, type="time"),
    }
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        merged = _merge_user_dim_overrides(useq_dims, overrides)

    assert merged[0].chunk_size == 1


def test_run_with_partial_dimension_overrides(
    core: CMMCorePlus, tmp_path: Path
) -> None:
    """User-provided chunk_size on partial dims carries through to the sink."""
    settings = AcquisitionSettings(
        root_path=str(tmp_path / "out.ome.zarr"),
        dimensions=[
            Dimension(name="t", chunk_size=1),
        ],
        overwrite=True,
    )
    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=3))
    core.mda.run(seq, output=settings)

    view = core.mda.get_view()
    assert view is not None
    assert view.shape[:-2] == (3,)
