#!/usr/bin/env python3

import tifffile
import useq
from ome_types import from_xml, validate_xml
from rich import print

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.metadata._ome import create_ome_metadata

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
    useq.MDASequence(
        axis_order="tpgzc",
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
    ),
    useq.MDASequence(
        axis_order="tpgzc",
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
    ),
    [
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
    ],
    useq.MDASequence(
        axis_order="tpgzc",
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
    ),
]


def test_ome_generation():
    mmc = CMMCorePlus()
    mmc.loadSystemConfiguration("tests/local_config.cfg")

    mmc.setConfig("Objective", "20X")  # px size 0.5 µm

    mmc.setROI(0, 0, 100, 200)

    mmc.setExposure(20)

    for idx, s in enumerate(SEQ):
        mmc.mda.run(s)

        assert mmc.mda.engine
        ome = create_ome_metadata(mmc.mda.engine._ome_path)

        if ome:
            print(f"\n-----------------SEQUENCE_{idx + 1}--------------------")
            print(ome.to_xml())
            validate_xml(ome.to_xml())
            print("-------------------------------------\n")


def test_ome_tif_example():
    mmc = CMMCorePlus()
    mmc.loadSystemConfiguration("tests/local_config.cfg")

    mmc.mda.run(SEQ[0], output="tests/test_multipos.ome.tif")

    assert mmc.mda.engine is not None
    print(create_ome_metadata(mmc.mda.engine._ome_path).to_xml())

    files = ["tests/test_multipos_p0.ome.tif", "tests/test_multipos_p1.ome.tif"]

    for fname in files:
        print(f"🔍 Checking OME metadata in: {fname}")
        print("=" * 60)

        try:
            with tifffile.TiffFile(fname) as tf:
                # Get OME-XML metadata
                ome_xml = tf.ome_metadata

                if ome_xml:
                    # Validate OME-XML
                    try:
                        validate_xml(ome_xml)
                        print("✅ OME-XML is schema-valid!")
                    except Exception as e:
                        print(f"❌ OME-XML validation failed: {e}")

                    # Show a snippet
                    print(from_xml(ome_xml).to_xml())

                else:
                    print("❌ No OME metadata found")

        except Exception as e:
            print(f"❌ Error reading TIFF file: {e}")

        print("\n")

    # delete test files
    import os
    for fname in [*files, "tests/test_multipos.ome.tif"]:
        if os.path.exists(fname):
            os.remove(fname)
            print(f"Deleted {fname}")
