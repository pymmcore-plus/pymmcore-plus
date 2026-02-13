import useq

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.handlers import StreamSettings

mmc = CMMCorePlus()
mmc.loadSystemConfiguration()

sequence = useq.MDASequence(
    channels=["DAPI", "FITC"],
    time_plan={"interval": 0.1, "loops": 3},
)

stream_settings_zarr = StreamSettings(
    root_path="example.ome.zarr", overwrite=True, asynchronous=True
)
stream_settings_tiff = StreamSettings(
    root_path="example.ome.tiff", overwrite=True, asynchronous=True
)

settings = [stream_settings_zarr, stream_settings_tiff]


mmc.run_mda(sequence, writer=settings)


# manual handler creation
# handler = OMERunnerHandler(stream_settings_zarr)
# mmc.run_mda(sequence, writer=handler)
