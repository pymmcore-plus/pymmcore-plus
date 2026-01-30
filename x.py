import useq
import yaozarrs
from ome_types import from_tiff

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.handlers import OMEWriterHandler


def new_func(zstore_1, tstore_1, vld):
    if vld == "zarr":
        yaozarrs.validate_zarr_store(zstore_1)
        print("✓ Zarr store is valid")

    elif vld == "tiff":
        files = [f"{tstore_1[:-9]}_p{pos:03d}.ome.tiff" for pos in range(2)]
        for idx, file in enumerate(files):
            from_tiff(file)
            print(f"✓ TIFF file {idx} is valid")


mmc = CMMCorePlus.instance()
mmc.loadSystemConfiguration("/Users/fdrgsp/Desktop/test_config.cfg")
mmc.setProperty("Objective", "Label", "Nikon 20X Plan Fluor ELWD")


zstore_1 = "/Users/fdrgsp/Desktop/out/test1.ome.zarr"
tstore_1 = "/Users/fdrgsp/Desktop/out/test1.ome.tiff"
zstore_2 = "/Users/fdrgsp/Desktop/out/test2.ome.zarr"
tstore_2 = "/Users/fdrgsp/Desktop/out/test2.ome.tiff"
zstore_3 = "/Users/fdrgsp/Desktop/out/test3.ome.zarr"
tstore_3 = "/Users/fdrgsp/Desktop/out/test3.ome.tiff"


# ------------------------------OPTION 1-----------------------------------------------
# stream, vld = OMEWriterHandler(zstore_1, backend="tensorstore", overwrite=True), "zarr"
stream, vld = OMEWriterHandler(tstore_1, backend="tifffile", overwrite=True), "tiff"


mmc.mda.events.sequenceStarted.connect(stream.sequenceStarted)
mmc.mda.events.frameReady.connect(stream.frameReady)
mmc.mda.events.sequenceFinished.connect(stream.sequenceFinished)

seq = useq.MDASequence(
    channels=["DAPI", "FITC"],
    stage_positions=((0, 0), (100, 100)),
    z_plan={"range": 2, "step": 0.4},
)

mmc.mda.run(seq)


new_func(zstore_1, tstore_1, vld)


# ------------------------------OPTION 2-----------------------------------------------
# stream, vld = OMEWriterHandler(zstore_2, backend="tensorstore", overwrite=True), "zarr"
stream, vld = OMEWriterHandler(tstore_2, backend="tifffile", overwrite=True), "tiff"

mmc.mda.run(seq, output=stream)

new_func(zstore_2, tstore_2, vld)

# ------------------------------OPTION 3-----------------------------------------------
# mmc.mda.run(seq, output=zstore_3)
mmc.mda.run(seq, output=tstore_3)

new_func(zstore_3, tstore_3, vld)
