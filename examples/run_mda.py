from useq import MDASequence

from pymmcore_plus import CMMCorePlus, MDA_multifile_tiff_writer

# see https://github.com/tlambert03/useq-schema
sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 50}],
    time_plan={"interval": 2, "loops": 5},
    z_plan={"range": 4, "step": 0.5},
    axis_order="tpcz",
)

<<<<<<< HEAD
mmc = CMMCorePlus.instance()
mmc.loadSystemConfiguration()


@mmc.mda.events.frameReady.connect
def new_frame(img, event):
    print(img.shape)


mda_thread = mmc.run_mda(sequence)
=======
mmc = CMMCorePlus()
mmc.loadSystemConfiguration("demo_config.cfg")

# create a writer to save the files
writer = MDA_multifile_tiff_writer("mda_data")
mmc.run_mda(sequence, writer)
>>>>>>> b4c1380 (Create MDAWriters submodule + multifile tiff writer)
