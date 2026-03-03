from __future__ import annotations

import math
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
import useq

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


def test_multicam_ome_sink_nonsequenced(multicam_core: CMMCorePlus) -> None:
    """Non-sequenced multi-camera MDA should write all frames to ome sink."""
    multicam_core.mda.engine.use_hardware_sequencing = False

    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=3))
    n_events = len(list(seq))  # 3
    n_cameras = multicam_core.getNumberOfCameraChannels()  # 2
    expected_frames = n_events * n_cameras  # 6

    multicam_core.mda.run(seq, output="scratch")

    view = multicam_core.mda.get_view()
    assert view is not None
    # The view should contain all frames (including both cameras)

    total_pixels = math.prod(view.shape)
    frame_pixels = view.shape[-2] * view.shape[-1]
    assert total_pixels // frame_pixels == expected_frames


def test_multicam_ome_sink_sequenced(multicam_core: CMMCorePlus) -> None:
    """Sequenced multi-camera MDA should write all frames to ome sink."""
    multicam_core.mda.engine.use_hardware_sequencing = True

    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=3))
    n_events = len(list(seq))  # 3
    n_cameras = multicam_core.getNumberOfCameraChannels()  # 2
    expected_frames = n_events * n_cameras  # 6

    multicam_core.mda.run(seq, output="scratch")

    view = multicam_core.mda.get_view()
    assert view is not None

    total_pixels = math.prod(view.shape)
    frame_pixels = view.shape[-2] * view.shape[-1]
    assert total_pixels // frame_pixels == expected_frames


def test_multicam_nonsequenced_events_missing_cam_index(
    multicam_core: CMMCorePlus,
) -> None:
    """Every frameReady event from a multi-camera MDA should have 'cam' index."""
    multicam_core.mda.engine.use_hardware_sequencing = False

    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=3))

    events: list = []
    multicam_core.mda.events.frameReady.connect(lambda img, ev, meta: events.append(ev))
    multicam_core.mda.run(seq)

    n_cameras = multicam_core.getNumberOfCameraChannels()
    assert len(events) == len(list(seq)) * n_cameras

    # Every event should have a `cam` key in its index
    for ev in events:
        assert "cam" in ev.index, (
            f"Event index {ev.index} is missing 'cam' key — "
            f"non-sequenced path doesn't add camera index"
        )


def test_multicam_event_index_consistency(multicam_core: CMMCorePlus) -> None:
    """Sequenced and non-sequenced runs should produce identical event indices."""
    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(interval=0, loops=3))

    def collect_indices(sequenced: bool) -> list[dict]:
        multicam_core.mda.engine.use_hardware_sequencing = sequenced
        indices: list[dict] = []
        mock = Mock(side_effect=lambda img, ev, meta: indices.append(dict(ev.index)))
        multicam_core.mda.events.frameReady.connect(mock)
        multicam_core.mda.run(seq)
        multicam_core.mda.events.frameReady.disconnect(mock)
        return indices

    seq_indices = collect_indices(sequenced=True)
    nonseq_indices = collect_indices(sequenced=False)

    assert len(seq_indices) == len(nonseq_indices), (
        f"Frame count mismatch: sequenced={len(seq_indices)}, "
        f"non-sequenced={len(nonseq_indices)}"
    )

    # Convert to comparable tuples and check they match
    def _to_tuples(indices: list[dict]) -> list[tuple]:
        return [tuple(sorted(d.items())) for d in indices]

    assert _to_tuples(seq_indices) == _to_tuples(nonseq_indices), (
        "Event indices differ between sequenced and non-sequenced paths.\n"
        f"  sequenced:     {seq_indices}\n"
        f"  non-sequenced: {nonseq_indices}"
    )


def test_multicam_ome_sink_with_channels_and_positions(
    multicam_core: CMMCorePlus,
) -> None:
    """Complex multi-camera MDA should write all frames to ome sink."""
    seq = useq.MDASequence(
        channels=["DAPI", "FITC"],
        stage_positions=[(0, 0, 0), (100, 100, 0)],
        time_plan=useq.TIntervalLoops(interval=0, loops=3),
        axis_order="tpcz",
    )

    n_events = len(list(seq))  # 2 * 2 * 3 = 12
    n_cameras = multicam_core.getNumberOfCameraChannels()  # 2
    expected_frames = n_events * n_cameras  # 24

    # Test both sequenced and non-sequenced
    for sequenced in (False, True):
        multicam_core.mda.engine.use_hardware_sequencing = sequenced
        label = "sequenced" if sequenced else "non-sequenced"

        # multi-cam + channels triggers a metadata limitation warning
        with pytest.warns(UserWarning, match="Multi-camera.*channels"):
            multicam_core.mda.run(seq, output="scratch")

        view = multicam_core.mda.get_view()
        assert view is not None, f"No view returned ({label})"

        total_pixels = math.prod(view.shape)
        frame_pixels = view.shape[-2] * view.shape[-1]
        actual_frames = total_pixels // frame_pixels
        assert actual_frames == expected_frames, (
            f"({label}) Expected {expected_frames} frames, got {actual_frames}. "
            f"view.shape={view.shape}"
        )
