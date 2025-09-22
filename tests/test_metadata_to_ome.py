#!/usr/bin/env python3

from math import prod

import pytest
import useq
from ome_types import validate_xml

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda._runner import GeneratorMDASequence
from pymmcore_plus.metadata._ome import create_ome_metadata

BASIC_SEQ = useq.MDASequence(
    time_plan=useq.TIntervalLoops(interval=0.5, loops=2),
    stage_positions=(
        useq.AbsolutePosition(x=100, y=100, name="FirstPosition"),
        useq.AbsolutePosition(x=200, y=200, name="SecondPosition"),
    ),
    z_plan=useq.ZRangeAround(range=3.0, step=1.0),
    channels=(
        useq.Channel(config="DAPI", exposure=20),
        useq.Channel(config="FITC", exposure=30),
        useq.Channel(config="DAPI", exposure=20),
    ),
)

PLATE_SEQ = useq.MDASequence(
    axis_order="pcz",
    stage_positions=useq.WellPlatePlan(
        plate=useq.WellPlate.from_str("96-well"),
        a1_center_xy=(0, 0),
        selected_wells=((0, 0, 0), (0, 1, 2)),
    ),
    z_plan=useq.ZRangeAround(range=3.0, step=1.0),
    channels=(
        useq.Channel(config="DAPI", exposure=20),
        useq.Channel(config="FITC", exposure=30),
    ),
)

GRID_SEQ = useq.MDASequence(
    time_plan=useq.TIntervalLoops(interval=0.5, loops=2),
    stage_positions=(
        useq.AbsolutePosition(x=100, y=100, name="FirstPosition"),
        useq.AbsolutePosition(x=200, y=200),
    ),
    channels=(
        useq.Channel(config="DAPI", exposure=20),
        useq.Channel(config="FITC", exposure=30),
        useq.Channel(config="DAPI", exposure=20),
    ),
    grid_plan=useq.GridRowsColumns(rows=2, columns=2),
)

SEQ_WITH_SUBSEQ_GRID = useq.MDASequence(
    stage_positions=(
        useq.AbsolutePosition(
            x=100,
            y=100,
            name="FirstPosition",
            sequence=useq.MDASequence(
                grid_plan=useq.GridRowsColumns(rows=2, columns=2)
            ),
        ),
        useq.AbsolutePosition(x=200, y=200, name="SecondPosition"),
    ),
    z_plan=useq.ZRangeAround(range=3.0, step=1.0),
    channels=(
        useq.Channel(config="DAPI", exposure=20),
        useq.Channel(config="FITC", exposure=30),
    ),
)


def _get_expected_images(seq: useq.MDASequence) -> int:
    expected_images = 0
    parent_grid = seq.grid_plan
    for pos in seq.stage_positions:
        sub_grid = pos.sequence.grid_plan if pos.sequence else None
        if plan := (sub_grid or parent_grid):
            num_pos = plan.num_positions()
        else:
            num_pos = 1
        expected_images += num_pos
    return expected_images


@pytest.mark.parametrize("seq", [BASIC_SEQ, PLATE_SEQ, GRID_SEQ, SEQ_WITH_SUBSEQ_GRID])
def test_ome_generation(seq: useq.MDASequence) -> None:
    mmc = CMMCorePlus()
    mmc.loadSystemConfiguration("tests/local_config.cfg")
    mmc.setConfig("Objective", "20X")  # px size 0.5 µm
    mmc.setROI(0, 0, 100, 200)

    engine = mmc.mda.engine
    assert engine is not None
    summary_meta = engine.get_summary_metadata(seq)
    frame_meta_list = [
        engine.get_frame_metadata(event, runner_time_ms=idx * 500)
        for idx, event in enumerate(seq)
    ]

    ome = create_ome_metadata(summary_meta, frame_meta_list)
    validate_xml(ome.to_xml())

    assert len(ome.images) == _get_expected_images(seq)
    sizes = [v for k, v in seq.sizes.items() if v and k not in {"p", "g"}]
    assert len(ome.images[0].pixels.planes) == prod(sizes)

    if isinstance((plan := seq.stage_positions), useq.WellPlatePlan):
        assert ome.plates is not None
        plate = ome.plates[0]
        assert plate.rows == plan.plate.rows
        assert plate.columns == plan.plate.columns
        assert len(plate.wells) == len(plan)


def test_ome_generation_from_events() -> None:
    mmc = CMMCorePlus()
    mmc.loadSystemConfiguration("tests/local_config.cfg")
    mmc.setConfig("Objective", "20X")  # px size 0.5 µm
    mmc.setROI(0, 0, 100, 200)

    seq = GeneratorMDASequence()
    events = [
        useq.MDAEvent(
            x_pos=10,
            y_pos=3,
            pos_name="p0",
            channel={"config": "DAPI", "exposure": 10},
            index={"c": 0},
        ),
        useq.MDAEvent(
            x_pos=11,
            y_pos=3,
            pos_name="p0",
            channel={"config": "FITC", "exposure": 20},
            index={"c": 1},
        ),
        useq.MDAEvent(
            x_pos=12,
            y_pos=3,
            pos_name="p0",
            channel={"config": "DAPI", "exposure": 15},
            index={"c": 0},
        ),
    ]

    engine = mmc.mda.engine
    assert engine is not None
    summary_meta = engine.get_summary_metadata(seq)
    summary_meta.pop("mda_sequence")  # this isn't actually mandatory

    frame_meta_list = [
        engine.get_frame_metadata(event, runner_time_ms=idx * 500)
        for idx, event in enumerate(events)
    ]

    ome = create_ome_metadata(summary_meta, frame_meta_list)
    validate_xml(ome.to_xml())

    assert len(ome.images) == 1
    assert len(ome.images[0].pixels.planes) == len(events)


def test_stupidly_empty_metadata() -> None:
    ome = create_ome_metadata({}, [])  # type: ignore
    validate_xml(ome.to_xml())
    assert len(ome.images) == 0
