"""Tests for MDA runner output/sink integration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
import useq
from ome_writers import AcquisitionSettings

from pymmcore_plus.mda._runner import MDARunner, _OmeWritersSink

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


def test_run_with_dimension_overrides(core: CMMCorePlus, tmp_path: Path) -> None:
    """dimension_overrides carries through to the written dimensions."""
    seq = useq.MDASequence(z_plan=useq.ZRangeAround(range=4, step=1))
    dest = tmp_path / "test.ome.zarr"
    core.mda.run(seq, output=dest, dimension_overrides={"z": {"chunk_size": 5}})
    metadata = json.loads((dest / "0" / "zarr.json").read_bytes())
    assert metadata["chunk_grid"]["configuration"]["chunk_shape"][0] == 5
