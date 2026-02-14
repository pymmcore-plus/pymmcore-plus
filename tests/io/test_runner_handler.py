from __future__ import annotations

import queue
from typing import TYPE_CHECKING
from unittest.mock import patch

import numpy as np
import pytest
import useq

from pymmcore_plus.mda.handlers import OMERunnerHandler, StreamSettings
from pymmcore_plus.mda.handlers._runner_handler import OMERunnerHandlerGroup

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
        asynchronous=False,
    )


@pytest.fixture
def tiff_settings(tmp_path: Path) -> StreamSettings:
    return StreamSettings(
        root_path=str(tmp_path / "test.ome.tiff"),
        overwrite=True,
        asynchronous=False,
    )


@pytest.fixture
def async_zarr_settings(tmp_path: Path) -> StreamSettings:
    return StreamSettings(
        root_path=str(tmp_path / "test_async.ome.zarr"),
        overwrite=True,
        asynchronous=True,
        queue_maxsize=50,
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
    assert s.dimensions is None
    assert s.dtype is None
    assert s.plate is None
    assert s.asynchronous is True
    assert s.queue_maxsize == 100


@pytest.mark.parametrize(
    "method",
    [
        "_validate_storage_order",
        "_validate_plate_positions",
        "_warn_chunk_buffer_memory",
    ],
)
def test_stream_settings_validators_skip_when_no_dims(
    tmp_path: Path, method: str
) -> None:
    s = StreamSettings(root_path=str(tmp_path / "out.ome.zarr"))
    result = getattr(s, method)()
    assert result is s


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
    assert handler.queue is not None
    assert isinstance(handler.queue, queue.Queue)


def test_handler_in_tempdir() -> None:
    settings = StreamSettings(root_path="test.ome.zarr", overwrite=True)
    handler = OMERunnerHandler.in_tempdir(settings)
    assert handler.stream_settings.root_path
    assert "pymmcp_ome_runner_" in str(handler.stream_settings.root_path)


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


def test_handler_write_error_propagates(
    async_zarr_settings: StreamSettings,
) -> None:
    handler = OMERunnerHandler(async_zarr_settings)
    handler._write_error = RuntimeError("test error")
    frame = np.zeros((512, 512), dtype=np.uint16)
    event = useq.MDAEvent()
    meta: dict = {"format": "frame-dict", "version": "1.0"}
    with pytest.raises(RuntimeError, match="Background writer failed"):
        handler._writeframe(frame, event, meta)  # type: ignore[arg-type]


def test_handler_drain_queue_returns_when_no_stream(
    async_zarr_settings: StreamSettings,
) -> None:
    handler = OMERunnerHandler(async_zarr_settings)
    assert handler._stream is None
    # _drain_queue should return immediately when stream is None
    handler._drain_queue()


def test_handler_enqueue_frame_full_queue_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    from pymmcore_plus._logger import logger as plog

    settings = StreamSettings(
        root_path=str(tmp_path / "full_q.ome.zarr"),
        overwrite=True,
        asynchronous=True,
        queue_maxsize=1,
    )
    handler = OMERunnerHandler(settings)
    frame = np.zeros((4, 4), dtype=np.uint16)
    event = useq.MDAEvent()
    meta: dict = {"format": "frame-dict", "version": "1.0"}

    # Fill the queue
    handler._queue.put(("dummy",))

    # Patch put to simulate Full on first timeout call, then succeed
    original_put = handler._queue.put
    call_count = 0

    def mock_put(item: object, timeout: float | None = None) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1 and timeout is not None:
            raise queue.Full
        # drain the queue first so the blocking put can succeed
        while not handler._queue.empty():
            try:
                handler._queue.get_nowait()
            except queue.Empty:
                break
        original_put(item)

    prev_level = plog.level
    plog.setLevel(logging.WARNING)
    try:
        with patch.object(handler._queue, "put", side_effect=mock_put):
            handler._enqueue_frame(frame, event, meta)  # type: ignore[arg-type]
    finally:
        plog.setLevel(prev_level)

    assert "Write queue full" in caplog.text


# ------------------- OMERunnerHandlerGroup -------------------


def test_group_empty() -> None:
    group = OMERunnerHandlerGroup()
    assert len(group) == 0
    assert not group
    assert list(group) == []
    assert group.get_handlers() == []


def test_group_with_handler(zarr_settings: StreamSettings) -> None:
    h = OMERunnerHandler(zarr_settings)
    group = OMERunnerHandlerGroup([h])
    assert len(group) == 1
    assert bool(group)
    assert list(group) == [h]
    assert group.get_handlers() == [h]


def test_group_cleanup_clears(zarr_settings: StreamSettings) -> None:
    h = OMERunnerHandler(zarr_settings)
    group = OMERunnerHandlerGroup([h])
    group.cleanup()
    assert len(group) == 0


# ------------------- integration with core.mda.run -------------------

MDA_SEQUENCES = [
    pytest.param(SIMPLE_MDA, id="simple"),
    pytest.param(MULTIPOINT_MDA, id="multipoint"),
    pytest.param(SUBSEQUENCE_GRID_MDA, id="subsequence-grid"),
]


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
def test_run_with_handler(
    tmp_path: Path, core: CMMCorePlus, mda: useq.MDASequence, asynchronous: bool
) -> None:
    settings = StreamSettings(
        root_path=str(tmp_path / "run.ome.zarr"),
        overwrite=True,
        asynchronous=asynchronous,
    )
    handler = OMERunnerHandler(settings)
    core.mda.run(mda, writer=handler)
    assert handler.stream is None


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
@pytest.mark.parametrize("ext", [".ome.zarr", ".ome.tiff"], ids=["zarr", "tiff"])
def test_run_writer_via_path(
    tmp_path: Path, core: CMMCorePlus, mda: useq.MDASequence, ext: str
) -> None:
    path = str(tmp_path / f"via_path{ext}")
    core.mda.run(mda, writer=path)


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_run_writer_via_stream_settings(
    tmp_path: Path, core: CMMCorePlus, mda: useq.MDASequence
) -> None:
    settings = StreamSettings(
        root_path=str(tmp_path / "via_settings.ome.zarr"),
        overwrite=True,
        asynchronous=False,
    )
    core.mda.run(mda, writer=settings)


def test_run_writer_invalid_path(core: CMMCorePlus) -> None:
    with pytest.raises(ValueError, match="Cannot infer writer format"):
        core.mda.run(SIMPLE_MDA, writer="/some/path.xyz")


@pytest.mark.parametrize("mda", MDA_SEQUENCES)
def test_run_multiple_writers(
    tmp_path: Path, core: CMMCorePlus, mda: useq.MDASequence
) -> None:
    settings_zarr = StreamSettings(
        root_path=str(tmp_path / "multi.ome.zarr"),
        overwrite=True,
        asynchronous=False,
    )
    settings_tiff = StreamSettings(
        root_path=str(tmp_path / "multi.ome.tiff"),
        overwrite=True,
        asynchronous=False,
    )
    core.mda.run(mda, writer=[settings_zarr, settings_tiff])


def test_run_no_writer(core: CMMCorePlus) -> None:
    core.mda.run(SIMPLE_MDA, writer=None)


def test_get_writer_handlers_empty(core: CMMCorePlus) -> None:
    assert len(core.mda.get_writer_handlers()) == 0


def test_group_delegates_to_both_handlers(
    zarr_settings: StreamSettings,
    tiff_settings: StreamSettings,
    core: CMMCorePlus,
) -> None:
    h_zarr = OMERunnerHandler(zarr_settings)
    h_tiff = OMERunnerHandler(tiff_settings)
    core.mda.run(SIMPLE_MDA, writer=[h_zarr, h_tiff])
    assert h_zarr.stream is None
    assert h_tiff.stream is None
