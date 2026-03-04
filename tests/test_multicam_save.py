from __future__ import annotations

from math import prod
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, Mock, patch

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

    with pytest.warns(UserWarning, match="Multi-camera.*channels"):
        multicam_core.mda.run(seq, output="scratch")

    view = multicam_core.mda.get_view()
    assert view is not None
    assert prod(view.shape[:-2]) == expected


def _sink_injected(runner: Any) -> MagicMock:
    """Inject a mock sink into an MDARunner for the duration of a run."""
    sink = MagicMock()
    sink.get_view.return_value = None
    real_coerce = runner._coerce_outputs

    def _coerce_with_sink(output: object = None, overwrite: bool = False) -> list:
        handlers = real_coerce(output, overwrite=overwrite)
        runner._sink = sink
        return handlers

    runner._coerce_outputs = _coerce_with_sink
    return sink


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

    sink = _sink_injected(multicam_core.mda)
    with patch.object(multicam_core.mda, "_engine", SkippingEngine()):
        multicam_core.mda.run([useq.MDAEvent()])

    n_cameras = multicam_core.getNumberOfCameraChannels()
    sink.skip.assert_called_once_with(frames=3 * n_cameras)
