#!/usr/bin/env python3

"""Test script for multi-position OME-TIFF acquisition."""
import tifffile
import useq
from ome_types import from_xml, validate_xml
from rich import print

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.handlers import OMETiffWriter

# Load the Micro-Manager configuration
mmc = CMMCorePlus()
mmc.loadSystemConfiguration("/Users/fdrgsp/Desktop/test_config.cfg")

print("✅ Configuration loaded successfully")

# Create a multi-position sequence with channels
seq = useq.MDASequence(
    axis_order="tpgzc",
    time_plan={"interval": 0.5, "loops": 2},
    stage_positions=[
        {"x": 100, "y": 100, "name": "FirstPosition"},
        useq.AbsolutePosition(
            x=200,
            y=200,
        ),
    ],
    z_plan={"range": 3.0, "step": 1.0},
    channels=[
        {"config": "DAPI"},
        {"config": "FITC"},
        {"config": "DAPI"},
    ],  # 2 channels
)


print(f"✅ Created multi-position sequence with UID: {seq.uid}")


print("🚀 Starting multi-position acquisition")

# Run the acquisition
mmc.mda.run(seq, output="/Users/fdrgsp/Desktop/test_multipos.ome.tif")

print("✅ Multi-position acquisition completed successfully")
print("🔍 Script completed")

assert mmc.mda.engine is not None
print(mmc.mda.engine.get_ome_metadata().to_xml())


files = [
    "/Users/fdrgsp/Desktop/test_multipos_p0.ome.tif",
    "/Users/fdrgsp/Desktop/test_multipos_p1.ome.tif",
]

for fname in files:
    print(f"🔍 Checking OME metadata in: {fname}")
    print("=" * 60)

    try:
        with tifffile.TiffFile(fname) as tf:
            # Get OME-XML metadata
            ome_xml = tf.ome_metadata

            if ome_xml:
                print("✅ OME metadata found!")

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
