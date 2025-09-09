#!/usr/bin/env python3
"""Test enhanced OME generation with proper Plane elements."""

import useq
from rich import print

from pymmcore_plus import CMMCorePlus


def test_ome_generation():
    """Test enhanced OME generation with proper Plane elements."""
    # Create a core instance with demo config
    mmc = CMMCorePlus()
    mmc.loadSystemConfiguration("/Users/fdrgsp/Desktop/test_config.cfg")

    mmc.setConfig("Objective", "20X")  # px size 0.5 µm

    mmc.setROI(0, 0, 100, 200)  # Set ROI to 512x512 pixels

    mmc.setExposure(20)

    sequence = useq.MDASequence(
        axis_order="tpgzc",
        time_plan={"interval": 0.5, "loops": 2},
        stage_positions=[
            {"x": 100, "y": 100, "name": "Pos0"},
            useq.AbsolutePosition(
                x=200,
                y=200,
                name="Pos1",
            )
        ],
        z_plan={"range": 3.0, "step": 1.0},
        channels=[
            {"config": "DAPI"},
            {"config": "FITC"},
            {"config": "DAPI"},
        ],  # 2 channels
        # grid_plan=useq.GridRowsColumns(rows=2, columns=2),
    )

    # sequence = [
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
    #         channel={"config": "FITC", "exposure": 10},
    #         index={"c": 1},
    #     ),
    #     useq.MDAEvent(
    #         x_pos=12,
    #         y_pos=3,
    #         pos_name="p0",
    #         channel={"config": "DAPI", "exposure": 10},
    #         index={"c": 0},
    #     ),
    # ]

    mmc.mda.run(sequence)

    assert mmc.mda.engine
    ome = mmc.mda.engine.get_ome_metadata()

    if ome:
        print()
        print(ome.to_xml())


if __name__ == "__main__":
    test_ome_generation()
