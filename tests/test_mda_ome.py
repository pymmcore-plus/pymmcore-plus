#!/usr/bin/env python3
"""Test enhanced OME generation with proper Plane elements."""

from rich import print
from useq import MDASequence

from pymmcore_plus import CMMCorePlus


def test_enhanced_ome_generation():
    """Test enhanced OME generation with proper Plane elements."""
    # Create a core instance with demo config
    mmc = CMMCorePlus()
    mmc.loadSystemConfiguration()

    mmc.setConfig("Objective", "20X")  # px size 0.5 µm

    mmc.setExposure(20)

    sequence = MDASequence(
        axis_order="tpzc",
        time_plan={"interval": 0.5, "loops": 2},  # 2 timepoints
        stage_positions=[
            {"x": 100, "y": 100, "name": "Pos0"},  # Position 1
            {"x": 200, "y": 200, "name": "Pos1"},  # Position 2
        ],
        z_plan={"range": 3.0, "step": 1.0},  # 4 z-slices: -1.5, -0.5, 0.5, 1.5
        channels=[{"config": "DAPI"}, {"config": "FITC"}],  # 2 channels
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
    ome_xml = mmc.mda.engine.get_sequence_ome_metadata(target_format="xml")

    if ome_xml:
        print(ome_xml)


if __name__ == "__main__":
    test_enhanced_ome_generation()
