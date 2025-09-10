#!/usr/bin/env python3

from math import prod

import useq
from ome_types import validate_xml

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.metadata._ome import (
    create_ome_metadata,
)

SEQ = [
    useq.MDASequence(
        axis_order="tpgzc",
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
    ),
    # useq.MDASequence(
    #     axis_order="tpgzc",
    #     time_plan=useq.TIntervalLoops(interval=0.5, loops=2),
    #     stage_positions=(
    #         useq.AbsolutePosition(x=100, y=100, name="FirstPosition"),
    #         useq.AbsolutePosition(x=200, y=200),
    #     ),
    #     channels=(
    #         useq.Channel(config="DAPI", exposure=20),
    #         useq.Channel(config="FITC", exposure=30),
    #         useq.Channel(config="DAPI", exposure=20),
    #     ),
    #     grid_plan=useq.GridRowsColumns(rows=2, columns=2),
    # ),
    # useq.MDASequence(
    #     axis_order="tpgzc",
    #     stage_positions=useq.WellPlatePlan(
    #         plate=useq.WellPlate.from_str("96-well"),
    #         a1_center_xy=(0, 0),
    #         selected_wells=((0, 0, 0), (0, 1, 2)),
    #     ),
    #     z_plan=useq.ZRangeAround(range=3.0, step=1.0),
    #     channels=(
    #         useq.Channel(config="DAPI", exposure=20),
    #         useq.Channel(config="FITC", exposure=30),
    #     ),
    # ),
    # [
    #     useq.MDAEvent(
    #         x_pos=10,
    #         y_pos=3,
    #         pos_name="p0",
    #         channel={"config": "DAPI", "exposure": 10},
    #         index={"c": 0},
    #     ),
    #     useq.MDAEvent(
    #         x_pos=11,
    #         y_pos=3,
    #         pos_name="p0",
    #         channel={"config": "FITC", "exposure": 20},
    #         index={"c": 1},
    #     ),
    #     useq.MDAEvent(
    #         x_pos=12,
    #         y_pos=3,
    #         pos_name="p0",
    #         channel={"config": "DAPI", "exposure": 15},
    #         index={"c": 0},
    #     ),
    # ],
    # useq.MDASequence(
    #     axis_order="tpgzc",
    #     stage_positions=(
    #         useq.AbsolutePosition(
    #             x=100,
    #             y=100,
    #             name="FirstPosition",
    #             sequence=useq.MDASequence(
    #                 grid_plan=useq.GridRowsColumns(rows=2, columns=2)
    #             ),
    #         ),
    #         useq.AbsolutePosition(x=200, y=200, name="SecondPosition"),
    #     ),
    #     z_plan=useq.ZRangeAround(range=3.0, step=1.0),
    #     channels=(
    #         useq.Channel(config="DAPI", exposure=20),
    #         useq.Channel(config="FITC", exposure=30),
    #     ),
    # ),
]

BASIC_SEQ = useq.MDASequence(
    axis_order="tpgzc",
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


def test_ome_generation():
    mmc = CMMCorePlus()
    mmc.loadSystemConfiguration("tests/local_config.cfg")
    mmc.setConfig("Objective", "20X")  # px size 0.5 µm
    mmc.setROI(0, 0, 100, 200)

    seq = BASIC_SEQ
    engine = mmc.mda.engine
    assert engine is not None
    summary_meta = engine.get_summary_metadata(seq)
    frame_meta_list = [
        engine.get_frame_metadata(event, runner_time_ms=idx * 500)
        for idx, event in enumerate(seq)
    ]

    ome = create_ome_metadata(summary_meta, frame_meta_list)
    validate_xml(ome.to_xml())
    assert len(ome.images) == len(seq.stage_positions)
    sizes = [v for k, v in seq.sizes.items() if v and k not in {"p"}]
    assert len(ome.images[0].pixels.planes) == prod(sizes)
