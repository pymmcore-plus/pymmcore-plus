import useq

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.handlers import StreamSettings

mmc = CMMCorePlus()
mmc.loadSystemConfiguration()

sequence = useq.MDASequence(channels=["DAPI", "FITC"])

stream_settings_zarr = StreamSettings(root_path="example.ome.zarr", overwrite=True)


# @mmc.mda.events.sequenceStarted.connect
# def info():
#     for h in mmc.mda.get_writer_handlers():
#         print(h)
#         print(h.stream_settings)
#         print(h.stream._backend)


# runner will create the handler
mmc.run_mda(sequence, writer=stream_settings_zarr)


# manual handler creation
# handler = OMERunnerHandler(stream_settings)
# mmc.run_mda(sequence, writer=handler)
