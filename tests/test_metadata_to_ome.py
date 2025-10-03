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

PLATE_SEQ_FOVS = useq.MDASequence(
    axis_order="pcz",
    stage_positions=useq.WellPlatePlan(
        plate=useq.WellPlate.from_str("96-well"),
        a1_center_xy=(0, 0),
        selected_wells=((0, 0, 0), (0, 1, 2)),
        well_points_plan=useq.GridRowsColumns(rows=1, columns=2),
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


def _verify_image_names(seq: useq.MDASequence, ome) -> None:
    """Verify that OME image names follow the _PositionKey naming convention."""
    # For well plate plans, verify well-based names
    if isinstance(seq.stage_positions, useq.WellPlatePlan):
        # Well plate positions use well names from the plan
        expected_names = []
        for idx, well_name in enumerate(
            [pos.name for pos in seq.stage_positions.image_positions]
        ):
            # Format: well_name_p{index:04d} or p{index:04d} if no name
            if well_name:
                expected_names.append(f"{well_name}_p{idx:04d}")
            else:
                expected_names.append(f"p{idx:04d}")

        actual_names = [img.name for img in ome.images]
        assert actual_names == expected_names, (
            f"Well plate image names mismatch.\n"
            f"Expected: {expected_names}\n"
            f"Actual: {actual_names}"
        )
        return

    # For regular positions with or without grids
    expected_names = []
    parent_grid = seq.grid_plan

    for p_idx, pos in enumerate(seq.stage_positions):
        pos_name = pos.name if hasattr(pos, "name") else None
        sub_grid = pos.sequence.grid_plan if pos.sequence else None
        grid_plan = sub_grid or parent_grid

        if grid_plan:
            # Has grid positions
            num_grid_positions = grid_plan.num_positions()
            for g_idx in range(num_grid_positions):
                if pos_name:
                    expected_names.append(f"{pos_name}_p{p_idx:04d}_g{g_idx:04d}")
                else:
                    expected_names.append(f"p{p_idx:04d}_g{g_idx:04d}")
        else:
            # No grid
            if pos_name:
                expected_names.append(f"{pos_name}_p{p_idx:04d}")
            else:
                expected_names.append(f"p{p_idx:04d}")

    actual_names = [img.name for img in ome.images]
    assert (
        actual_names == expected_names
    ), f"Image names mismatch.\nExpected: {expected_names}\nActual: {actual_names}"


@pytest.mark.parametrize(
    # "seq", [BASIC_SEQ, PLATE_SEQ, PLATE_SEQ_FOVS, GRID_SEQ, SEQ_WITH_SUBSEQ_GRID]
    "seq", [PLATE_SEQ, PLATE_SEQ_FOVS]
)
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

    # enable for debugging
    from rich import print
    print(ome.to_xml())

    assert len(ome.images) == _get_expected_images(seq)
    sizes = [v for k, v in seq.sizes.items() if v and k not in {"p", "g"}]
    assert len(ome.images[0].pixels.planes) == prod(sizes)

    # Verify image names follow the _PositionKey naming convention
    _verify_image_names(seq, ome)

    pixels = ome.images[0].pixels
    assert pixels.metadata_only is None
    assert pixels.tiff_data_blocks is not None
    assert len(pixels.tiff_data_blocks) == len(pixels.planes)

    for tiff_data, plane in zip(pixels.tiff_data_blocks, pixels.planes):
        assert tiff_data.first_z == plane.the_z
        assert tiff_data.first_c == plane.the_c
        assert tiff_data.first_t == plane.the_t
        assert tiff_data.plane_count == 1

    if isinstance((plan := seq.stage_positions), useq.WellPlatePlan):
        assert ome.plates is not None
        plate = ome.plates[0]
        assert plate.rows == plan.plate.rows
        assert plate.columns == plan.plate.columns

        # Count total WellSamples across all wells
        total_well_samples = sum(
            len(well.well_samples) if well.well_samples else 0
            for well in plate.wells
        )
        # Total WellSamples should equal total image positions (including FOVs)
        assert total_well_samples == len(plan)


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
    # Verify the image name follows _PositionKey convention: "p0_p0000"
    assert ome.images[0].name == "p0_p0000"
    assert len(ome.images[0].pixels.planes) == len(events)

    pixels = ome.images[0].pixels
    assert pixels.metadata_only is None
    assert pixels.tiff_data_blocks is not None
    assert len(pixels.tiff_data_blocks) == len(pixels.planes)

    for tiff_data, plane in zip(pixels.tiff_data_blocks, pixels.planes):
        assert tiff_data.first_z == plane.the_z
        assert tiff_data.first_c == plane.the_c
        assert tiff_data.first_t == plane.the_t
        assert tiff_data.plane_count == 1


def test_stupidly_empty_metadata() -> None:
    ome = create_ome_metadata({}, [])  # type: ignore
    validate_xml(ome.to_xml())
    assert len(ome.images) == 0


@pytest.mark.parametrize(
    "axis_order,expected_dimension_order",
    [
        # Test cases that verify the mapping from useq iteration order
        # to OME rasterization order (reversed)
        ("tpzc", "XYCZT"),  # t->p->z->c becomes C fastest, Z, T slowest
        ("tpcz", "XYZCT"),  # t->p->c->z becomes Z fastest, C, T slowest
        ("pcz", "XYZCT"),  # p->c->z becomes Z fastest, C slowest (T added)
        ("pzc", "XYCZT"),  # p->z->c becomes C fastest, Z slowest (T added)
        ("zcpt", "XYTCZ"),  # z->c->p->t becomes T fastest, C, Z slowest
        ("czpt", "XYTZC"),  # c->z->p->t becomes T fastest, Z, C slowest
        ("tc", "XYCTZ"),  # t->c becomes C fastest, T slowest (Z added at end)
        ("ct", "XYTCZ"),  # c->t becomes T fastest, C slowest (Z added at end)
        ("z", "XYZCT"),  # z only becomes Z fastest (C,T added at end)
        ("c", "XYCZT"),  # c only becomes C fastest (Z,T added)
        ("t", "XYTCZ"),  # t only becomes T fastest (C,Z added)
    ],
)
def test_dimension_order_from_axis_order(
    axis_order: str, expected_dimension_order: str
) -> None:
    """Test that useq axis_order is correctly converted to OME DimensionOrder.

    useq axis_order represents iteration order (outermost to innermost loop),
    while OME DimensionOrder represents rasterization order (fastest to slowest
    varying dimension). The mapping should reverse the filtered axes.
    """
    from ome_types.model import Pixels_DimensionOrder

    from pymmcore_plus.metadata._ome import _extract_dimension_order_from_sequence

    # Create a sequence with the specified axis order
    seq = useq.MDASequence(axis_order=tuple(axis_order))

    # Extract the dimension order
    result = _extract_dimension_order_from_sequence(seq)

    # Verify it matches the expected OME dimension order
    expected = getattr(Pixels_DimensionOrder, expected_dimension_order)
    assert result == expected, (
        f"For axis_order='{axis_order}', expected {expected_dimension_order} "
        f"but got {result}"
    )


def test_dimension_order_iteration_vs_rasterization() -> None:
    """Test relationship between iteration and rasterization order."""
    from pymmcore_plus.metadata._ome import _extract_dimension_order_from_sequence

    # Create a sequence with axis_order="tpzc"
    seq = useq.MDASequence(
        axis_order=("t", "p", "z", "c"),
        time_plan=useq.TIntervalLoops(interval=0, loops=2),
        stage_positions=(useq.Position(x=0, y=0),),
        z_plan=useq.ZRangeAround(range=2, step=1),
        channels=(
            useq.Channel(config="DAPI", exposure=10),
            useq.Channel(config="FITC", exposure=10),
        ),
    )  # Get the dimension order
    dimension_order = _extract_dimension_order_from_sequence(seq)
    assert str(dimension_order) == "Pixels_DimensionOrder.XYCZT"

    # Verify this matches the actual iteration pattern
    events = list(seq)[:6]  # First 6 events for one position

    # Check that C varies fastest (0->1 in consecutive events)
    assert events[0].index.get("c", 0) == 0
    assert events[1].index.get("c", 0) == 1
    assert events[0].index.get("z", 0) == events[1].index.get("z", 0)  # Z same
    assert events[0].index.get("t", 0) == events[1].index.get("t", 0)  # T same

    # Check that Z varies next (changes when C completes a cycle)
    assert events[2].index.get("z", 0) == 1  # Z increased
    assert events[2].index.get("c", 0) == 0  # C reset to 0
    assert events[2].index.get("t", 0) == 0  # T still same
