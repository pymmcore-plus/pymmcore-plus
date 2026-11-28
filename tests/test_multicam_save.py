from __future__ import annotations

from math import prod
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock, call, patch

import numpy as np
import pytest
import useq

from pymmcore_plus.core._sequencing import SequencedEvent
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
    if sequenced and axis_order == "tpcz":
        # with channels innermost (tpzc) the channel changes every frame, so the
        # z-stack cannot be sequenced and the engine falls back to single events
        _enable_z_sequencing(core, seq)

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


@pytest.mark.parametrize(
    "channels, expected",
    [
        (
            ["DAPI", "FITC"],
            ["DAPI-Camera", "DAPI-Camera2", "FITC-Camera", "FITC-Camera2"],
        ),
        ([], ["Camera", "Camera2"]),
    ],
)
def test_multicam_channel_names(
    multicam_core: CMMCorePlus, channels: list[str], expected: list[str]
) -> None:
    """Folded channels are named like Micro-Manager's: <channel>-<camera>.

    Without channels, they are named after the cameras alone.
    """
    from pymmcore_plus.mda._sink import OmeWritersSink

    seq = useq.MDASequence(channels=channels)
    meta = multicam_core.mda.engine.setup_sequence(seq)
    assert meta is not None
    assert meta["image_infos"][0]["camera_channel_names"] == ("Camera", "Camera2")

    sink = OmeWritersSink.from_output("scratch")
    sink.setup(seq, meta)
    c_dim = next(d for d in sink._settings.dimensions if d.name == "c")
    assert c_dim.coords is not None
    assert [ch.name for ch in c_dim.coords] == expected  # type: ignore[union-attr]
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
    storage, reorder = _fold_cameras_into_channels(dims, [["A", "B"], ["A", "B"]])
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


def _enable_z_sequencing(core: CMMCorePlus, seq: useq.MDASequence) -> None:
    """Make the demo Z stage sequenceable, so z-stacks really are SequencedEvents."""
    core.setProperty("Z", "UseSequences", "Yes")
    events = list(core.mda.engine.event_iterator(seq))
    assert events
    assert all(isinstance(e, SequencedEvent) for e in events)


def _define_camera_presets(core: CMMCorePlus) -> None:
    core.defineConfig("Cams", "Both", "Core", "Camera", "MultiCam")
    core.defineConfig("Cams", "Single", "Core", "Camera", "Camera")


@pytest.mark.parametrize("sequenced", [True, False])
@pytest.mark.parametrize("first", ["Both", "Single"])
def test_mixed_multi_and_single_camera_channels(
    multicam_core: CMMCorePlus, sequenced: bool, first: str
) -> None:
    """A Multi Camera channel and a single-camera channel in one sequence.

    The Multi Camera channel yields two frames per event and the other one, so
    each channel gets as many entries in the channel axis as it has cameras, and
    every frame must land in its own slot.
    """
    core = multicam_core
    core.mda.engine.use_hardware_sequencing = sequenced
    _define_camera_presets(core)
    configs = ["Both", "Single"] if first == "Both" else ["Single", "Both"]
    seq = useq.MDASequence(
        channels=[useq.Channel(group="Cams", config=c) for c in configs],
        time_plan=useq.TIntervalLoops(interval=0, loops=2),
        z_plan=useq.ZRangeAround(range=2, step=1),
    )
    if sequenced:
        _enable_z_sequencing(core, seq)
    # storage channel of each (channel index, camera index)
    entries = {"Both": ["Both-Camera", "Both-Camera2"], "Single": ["Single"]}
    expected_names = [n for c in configs for n in entries[c]]
    slot = {}
    for c, config in enumerate(configs):
        for cam in range(len(entries[config])):
            slot[(c, cam)] = len(slot)

    frames: dict[tuple[int, int, int, int], np.ndarray] = {}

    def _collect(img: np.ndarray, event: useq.MDAEvent, _meta: dict) -> None:
        i = event.index
        frames[(i["t"], i["c"], i["z"], i.get("cam", 0))] = img.copy()

    core.mda.events.frameReady.connect(_collect)
    core.mda.run(seq, output="scratch")
    core.mda.events.frameReady.disconnect(_collect)

    view = core.mda.get_view()
    assert view is not None
    assert view.shape[:-2] == (2, 3, 3)
    sink = core.mda._sink
    c_dim = next(d for d in sink._settings.dimensions if d.name == "c")  # type: ignore[union-attr]
    assert [ch.name for ch in c_dim.coords] == expected_names  # type: ignore[union-attr]

    assert len(frames) == 2 * 3 * 3  # t * (2 + 1 camera frames) * z
    for (t, c, z, cam), img in frames.items():
        np.testing.assert_array_equal(np.asarray(view[t, slot[(c, cam)], z]), img)


def test_mixed_cameras_skip_event_frames(multicam_core: CMMCorePlus) -> None:
    """A skipped event skips as many frames as its own channel's camera yields."""
    core = multicam_core
    _define_camera_presets(core)
    real_engine = core.mda.engine

    class SkippingEngine:
        def setup_sequence(self, sequence: useq.MDASequence) -> dict:
            return real_engine.setup_sequence(sequence)

        def setup_event(self, event: useq.MDAEvent) -> None:
            raise SkipEvent(num_frames=1)

        def exec_event(self, event: useq.MDAEvent) -> tuple:
            return ()

    seq = useq.MDASequence(
        channels=[
            useq.Channel(group="Cams", config="Both"),
            useq.Channel(group="Cams", config="Single"),
        ]
    )
    sink = MagicMock()
    with (
        patch.object(core.mda, "_engine", SkippingEngine()),
        patch.object(core.mda, "_coerce_outputs", return_value=([], sink)),
    ):
        core.mda.run(seq)

    assert sink.skip.call_args_list == [call(frames=2), call(frames=1)]


def test_mixed_cameras_need_camera_in_every_preset(multicam_core: CMMCorePlus) -> None:
    """Which camera a preset without Core-Camera uses is ambiguous: fail early.

    Without Core-Camera, DAPI keeps whatever camera was selected before it, which
    yields one frame here (after Single) or two (after Both, at the next timepoint).
    """
    core = multicam_core
    _define_camera_presets(core)
    seq = useq.MDASequence(
        channels=[
            useq.Channel(group="Cams", config="Both"),
            useq.Channel(group="Cams", config="Single"),
            "DAPI",
        ],
    )
    with pytest.raises(ValueError, match=r"must then set Core-Camera.*Channel/DAPI"):
        core.mda.run(seq, output="scratch")


def test_preset_without_camera_keeps_it_when_unambiguous(
    multicam_core: CMMCorePlus,
) -> None:
    """With one frame count for every camera, presets need not set Core-Camera."""
    core = multicam_core
    _define_camera_presets(core)
    seq = useq.MDASequence(channels=[useq.Channel(group="Cams", config="Both"), "DAPI"])
    core.mda.run(seq, output="scratch")
    view = core.mda.get_view()
    assert view is not None
    assert view.shape[:-2] == (4,)  # DAPI keeps the Multi Camera: 2 + 2 entries


@pytest.mark.parametrize("sequenced", [True, False])
def test_mixed_cameras_skipped_events(
    multicam_core: CMMCorePlus, sequenced: bool
) -> None:
    """Skipping the Multi Camera channel's events skips two frames per event.

    With Z sequencing, each skipped event is a whole z-stack (SequencedEvent), and
    SkipEvent.num_frames counts its sub-events.
    """
    core = multicam_core
    core.mda.engine.use_hardware_sequencing = sequenced
    _define_camera_presets(core)
    seq = useq.MDASequence(
        channels=[
            useq.Channel(group="Cams", config="Both"),
            useq.Channel(group="Cams", config="Single"),
        ],
        time_plan=useq.TIntervalLoops(interval=0, loops=2),
        z_plan=useq.ZRangeAround(range=2, step=1),
    )
    if sequenced:
        _enable_z_sequencing(core, seq)

    engine = core.mda.engine
    real_setup_event = engine.setup_event

    def setup_event(event: useq.MDAEvent) -> None:
        # skip the Multi Camera channel at t=0 (a SequencedEvent's own index is
        # empty; its sub-events carry the indices)
        sub_events = getattr(event, "events", [event])
        assert event.channel is not None
        if event.channel.config == "Both" and sub_events[0].index["t"] == 0:
            raise SkipEvent(num_frames=len(sub_events))
        real_setup_event(event)

    frames: dict[tuple[int, int, int, int], np.ndarray] = {}

    def _collect(img: np.ndarray, event: useq.MDAEvent, _meta: dict) -> None:
        i = event.index
        frames[(i["t"], i["c"], i["z"], i.get("cam", 0))] = img.copy()

    core.mda.events.frameReady.connect(_collect)
    with patch.object(engine, "setup_event", setup_event):
        core.mda.run(seq, output="scratch")
    core.mda.events.frameReady.disconnect(_collect)

    view = core.mda.get_view()
    assert view is not None
    assert view.shape[:-2] == (2, 3, 3)
    # t=0 of Both (2 cameras x 3 z) was skipped: 18 - 6 frames acquired
    assert len(frames) == 12
    slot = {(0, 0): 0, (0, 1): 1, (1, 0): 2}
    for (t, c, z, cam), img in frames.items():
        np.testing.assert_array_equal(np.asarray(view[t, slot[(c, cam)], z]), img)
    # the skipped slots hold no data, and nothing spilled into them
    assert not np.asarray(view[0, 0:2]).any()


@pytest.mark.parametrize(
    "delivered",
    [(3, 1), (1, 3), (2, 1), (1, 1)],
    ids=["cam1-short", "cam0-short", "both-short", "both-one"],
)
def test_multicam_dropped_frames_in_z_sequence(
    multicam_core: CMMCorePlus, delivered: tuple[int, int]
) -> None:
    """Frames dropped by a camera within a Z sequence leave only their own slots empty.

    A camera that comes up short is missing its last planes (frames are assigned to
    planes by each camera's frame count). The engine then emits the complete planes,
    then the other cameras' remaining frames back to back, then one skip per missing
    frame -- this reproduces that output for the first timepoint's z-stack.
    """
    from pymmcore_plus.mda._sink import OmeWritersSink

    core = multicam_core
    n_z, n_cam = 3, 2
    seq = useq.MDASequence(
        time_plan=useq.TIntervalLoops(interval=0, loops=2),
        z_plan=useq.ZRangeAround(range=2, step=1),
    )
    sink = OmeWritersSink.from_output("scratch")
    sink.setup(seq, core.mda.engine.setup_sequence(seq))
    meta = {"runner_time_ms": 0.0, "exposure_ms": 1.0}
    shape = (core.getImageHeight(), core.getImageWidth())

    def value(t: int, z: int, cam: int) -> int:
        return 100 * t + 10 * z + cam + 1

    def append(t: int, z: int, cam: int) -> None:
        img = np.full(shape, value(t, z, cam), dtype=np.uint16)
        sink.append(img, useq.MDAEvent(index={"t": t, "z": z, "cam": cam}), meta)  # type: ignore[arg-type]

    # t=0: one Z sequence in which camera `cam` delivers only `delivered[cam]` planes
    complete = min(delivered)
    for z in range(complete):
        for cam in range(n_cam):
            append(0, z, cam)
    for z in range(complete, n_z):  # flush_remaining(): incomplete planes, sorted
        for cam in range(n_cam):
            if z < delivered[cam]:
                append(0, z, cam)
    sink.skip(frames=n_z * n_cam - sum(delivered))  # validate_count()'s missing frames
    # t=1: complete
    for z in range(n_z):
        for cam in range(n_cam):
            append(1, z, cam)
    sink.close()

    view = sink.get_view()
    assert view is not None
    for t in range(2):
        for cam in range(n_cam):
            got = [int(np.asarray(view[t, cam, z]).flat[0]) for z in range(n_z)]
            expected = [
                value(t, z, cam) if t == 1 or z < delivered[cam] else 0
                for z in range(n_z)
            ]
            assert got == expected, (t, cam)
