from __future__ import annotations

from math import prod
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest
import useq

from pymmcore_plus.mda._runner import SkipEvent

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


@pytest.fixture
def multicam_core(core: CMMCorePlus) -> CMMCorePlus:
    """CMMCorePlus with DemoCamera multi-camera setup (2 cameras)."""
    core.loadDevice("Camera2", "DemoCamera", "DCam")
    core.loadDevice("MultiCam", "Utilities", "Multi Camera")
    core.initializeDevice("MultiCam")
    core.initializeDevice("Camera2")
    core.setProperty("Camera2", "BitDepth", "16")
    core.setProperty("MultiCam", "Physical Camera 1", "Camera")
    core.setProperty("MultiCam", "Physical Camera 2", "Camera2")
    core.setCameraDevice("MultiCam")
    return core


@pytest.mark.parametrize("sequenced", [True, False])
def test_multicam_ome_sink(multicam_core: CMMCorePlus, sequenced: bool) -> None:
    """Multi-camera MDA should write all N*M frames to the ome sink."""
    multicam_core.mda.engine.use_hardware_sequencing = sequenced

    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=3))
    expected = len(list(seq)) * multicam_core.getNumberOfCameraChannels()

    multicam_core.mda.run(seq, output="scratch")

    view = multicam_core.mda.get_view()
    assert view is not None
    assert prod(view.shape[:-2]) == expected


def test_multicam_event_indices(multicam_core: CMMCorePlus) -> None:
    """Both paths should emit cam-indexed events with identical indices."""
    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=3))
    n_expected = len(list(seq)) * multicam_core.getNumberOfCameraChannels()

    def collect_indices(sequenced: bool) -> list[dict]:
        multicam_core.mda.engine.use_hardware_sequencing = sequenced
        indices: list[dict] = []
        cb = Mock(side_effect=lambda _i, ev, _m: indices.append(dict(ev.index)))
        multicam_core.mda.events.frameReady.connect(cb)
        multicam_core.mda.run(seq)
        multicam_core.mda.events.frameReady.disconnect(cb)
        return indices

    seq_idx = collect_indices(sequenced=True)
    nonseq_idx = collect_indices(sequenced=False)

    # both should have the right count
    assert len(seq_idx) == len(nonseq_idx) == n_expected

    # every event must have a cam key
    for idx in seq_idx + nonseq_idx:
        assert "cam" in idx

    # indices must match across paths
    to_tuples = [tuple(sorted(d.items())) for d in seq_idx]
    assert to_tuples == [tuple(sorted(d.items())) for d in nonseq_idx]


@pytest.mark.parametrize("sequenced", [True, False])
def test_multicam_ome_sink_with_channels(
    multicam_core: CMMCorePlus, sequenced: bool
) -> None:
    """Multi-camera + optical channels should write all frames to ome sink."""
    multicam_core.mda.engine.use_hardware_sequencing = sequenced

    seq = useq.MDASequence(
        channels=["DAPI", "FITC"],
        stage_positions=[(0, 0, 0), (100, 100, 0)],
        time_plan=useq.TIntervalLoops(interval=0, loops=3),
        axis_order="tpcz",
    )
    expected = len(list(seq)) * multicam_core.getNumberOfCameraChannels()

    multicam_core.mda.run(seq, output="scratch")

    view = multicam_core.mda.get_view()
    assert view is not None
    assert prod(view.shape[:-2]) == expected


def test_multicam_skip_event_multiplier(multicam_core: CMMCorePlus) -> None:
    """SkipEvent.num_frames should be multiplied by n_cameras for the sink."""
    real_engine = multicam_core.mda.engine

    class SkippingEngine:
        """Delegates setup_sequence for real metadata, skips every event."""

        def setup_sequence(self, sequence: useq.MDASequence) -> dict:
            return real_engine.setup_sequence(sequence)

        def setup_event(self, event: useq.MDAEvent) -> None:
            raise SkipEvent(num_frames=3)

        def exec_event(self, event: useq.MDAEvent) -> tuple:
            return ()

    sink = MagicMock()
    with (
        patch.object(multicam_core.mda, "_engine", SkippingEngine()),
        patch.object(multicam_core.mda, "_coerce_outputs", return_value=([], sink)),
    ):
        multicam_core.mda.run([useq.MDAEvent()])

    n_cameras = multicam_core.getNumberOfCameraChannels()
    sink.skip.assert_called_once_with(frames=3 * n_cameras)


@pytest.mark.parametrize("sequenced", [True, False])
def test_multicam_selected_by_channel_preset(
    multicam_core: CMMCorePlus, sequenced: bool
) -> None:
    """The sink must be sized for the camera the channels select, not the current one.

    Here a single camera is current when the sequence starts, and the channel preset
    switches Core-Camera to the Multi Camera, so every event yields two frames.
    """
    core = multicam_core
    core.mda.engine.use_hardware_sequencing = sequenced
    core.defineConfig("Cams", "Both", "Core", "Camera", "MultiCam")
    core.defineConfig("Cams", "Single", "Core", "Camera", "Camera")
    core.setCameraDevice("Camera")

    seq = useq.MDASequence(
        channels=[useq.Channel(group="Cams", config="Both")],
        time_plan=useq.TIntervalLoops(interval=0, loops=3),
    )
    # the selected camera is a single camera, but the channel's is not
    expected = len(list(seq)) * 2

    core.mda.run(seq, output="scratch")

    view = core.mda.get_view()
    assert view is not None
    assert prod(view.shape[:-2]) == expected


@pytest.mark.parametrize("sequenced", [True, False])
@pytest.mark.parametrize("axis_order", ["tpcz", "tpzc"])
def test_multicam_folds_cameras_into_channels(
    multicam_core: CMMCorePlus, sequenced: bool, axis_order: str
) -> None:
    """Cameras are stored as channels (t, c*cam, z, y, x), each frame in its slot.

    OME allows at most 5 non-position axes, so t, c, z and a camera axis cannot
    all be separate. Frames arrive camera-innermost and must be reordered.
    """
    core = multicam_core
    core.mda.engine.use_hardware_sequencing = sequenced
    seq = useq.MDASequence(
        channels=["DAPI", "FITC"],
        time_plan=useq.TIntervalLoops(interval=0, loops=2),
        z_plan=useq.ZRangeAround(range=2, step=1),
        axis_order=axis_order,
    )

    frames: dict[tuple[int, int, int, int], np.ndarray] = {}

    def _collect(img: np.ndarray, event: useq.MDAEvent, _meta: dict) -> None:
        i = event.index
        frames[(i["t"], i["c"], i["z"], i["cam"])] = img.copy()

    core.mda.events.frameReady.connect(_collect)
    core.mda.run(seq, output="scratch")
    core.mda.events.frameReady.disconnect(_collect)

    view = core.mda.get_view()
    assert view is not None
    n_t, n_c, n_z, n_cam = 2, 2, 3, 2
    if axis_order == "tpcz":
        assert view.shape[:-2] == (n_t, n_c * n_cam, n_z)
    else:  # channels innermost: stored as acquired, z before c
        assert view.shape[:-2] == (n_t, n_z, n_c * n_cam)
    assert len(frames) == n_t * n_c * n_z * n_cam
    for (t, c, z, cam), img in frames.items():
        ch = c * n_cam + cam
        idx = (t, ch, z) if axis_order == "tpcz" else (t, z, ch)
        np.testing.assert_array_equal(np.asarray(view[idx]), img)


def test_multicam_channel_names(multicam_core: CMMCorePlus) -> None:
    """Folded channels are named <channel>/<physical camera>."""
    from pymmcore_plus.mda._sink import OmeWritersSink

    seq = useq.MDASequence(channels=["DAPI", "FITC"])
    sink = OmeWritersSink.from_output("scratch")
    sink.setup(seq, multicam_core.mda.engine.setup_sequence(seq))
    c_dim = next(d for d in sink._settings.dimensions if d.name == "c")
    names = [ch.name for ch in c_dim.coords]
    assert names == ["DAPI/Camera", "DAPI/Camera2", "FITC/Camera", "FITC/Camera2"]
    sink.close()


def test_frame_reorderer_skips_and_flush() -> None:
    """Skipped frames keep their slots; a run that ends early still writes."""
    from ome_writers import Dimension

    from pymmcore_plus.mda._sink import _fold_cameras_into_channels

    dims = [
        Dimension(name="c", count=2, type="channel"),
        Dimension(name="z", count=3, type="space"),
        Dimension(name="y", count=1, type="space"),
        Dimension(name="x", count=1, type="space"),
    ]
    storage, reorder = _fold_cameras_into_channels(dims, ["A", "B"])
    assert [d.name for d in storage] == ["c", "z", "y", "x"]
    assert storage[0].count == 4

    written: list[object] = []
    stream = MagicMock()
    stream.append.side_effect = lambda f, **_: written.append(int(f[0, 0]))
    stream.skip.side_effect = lambda frames: written.extend(["skip"] * frames)

    # arrival order (c, z, cam): label each frame by its arrival index
    for k in range(9):  # stop partway through c=1 (z=1, cam=0)
        if k == 4:
            reorder.push(stream, None, None)  # skipped: c=0, z=2, cam=0
        else:
            reorder.push(stream, np.full((1, 1), k), {})
    reorder.flush(stream)
    # storage order (c*cam, z): c0/A z0..2, c0/B z0..2, c1/A z0..2, c1/B z0..2.
    # c1/A z2 never arrived, so flush() skips it before writing the held c1/B z0.
    assert written == [0, 2, "skip", 1, 3, 5, 6, 8, "skip", 7]
