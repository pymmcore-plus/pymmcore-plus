#!/usr/bin/env python3
"""Test enhanced OME generation with proper Plane elements."""

import useq
from rich import print

from pymmcore_plus import CMMCorePlus


def test_enhanced_ome_generation():
    """Test enhanced OME generation with proper Plane elements."""
    # Create a core instance with demo config
    mmc = CMMCorePlus()
    mmc.loadSystemConfiguration("/Users/fdrgsp/Desktop/test_config.cfg")

    mmc.setConfig("Objective", "20X")  # px size 0.5 µm

    mmc.setROI(0, 0, 100, 200)  # Set ROI to 512x512 pixels

    mmc.setExposure(20)

    sequence = useq.MDASequence(
        axis_order="tpgcz",
        time_plan={"interval": 0.5, "loops": 2},  # 2 timepoints
        stage_positions=[
            {"x": 100, "y": 100, "name": "Pos0"},  # Position 1
            {"x": 200, "y": 200, "name": "Pos1"},  # Position 2
        ],
        z_plan={"range": 3.0, "step": 1.0},  # 4 z-slices: -1.5, -0.5, 0.5, 1.5
        channels=[
            {"config": "DAPI"},
            {"config": "FITC"},
            {"config": "DAPI"},
        ],  # 2 channels
        # grid_plan=useq.GridRowsColumns(rows=2, columns=2),  # 2 rows, 2 columns
    )

    # sequence = MDASequence(
    #     axis_order="tpzgc",
    #     stage_positions=[
    #         {"x": 100, "y": 100, "name": "Pos0"},  # Position 1
    #         {"x": 200, "y": 200, "name": "Pos1"},  # Position 2
    #     ],
    #     # z_plan={"range": 3.0, "step": 1.0},  # 4 z-slices: -1.5, -0.5, 0.5, 1.5
    #     grid_plan=useq.GridRowsColumns(rows=2, columns=2),  # 2 rows, 2 columns
    #     channels=[{"config": "DAPI"}, {"config": "FITC"}],  # 2 channels
    # )

    mmc.mda.run(sequence)

    assert mmc.mda.engine
    ome_xml = mmc.mda.engine.get_ome_metadata(target_format="xml")

    if ome_xml:
        print()
        print(ome_xml)


if __name__ == "__main__":
    test_enhanced_ome_generation()
