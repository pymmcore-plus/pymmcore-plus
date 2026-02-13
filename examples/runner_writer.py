import useq

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.handlers import OMERunnerHandler, StreamSettings  # noqa: F401

mmc = CMMCorePlus()
mmc.loadSystemConfiguration()

sequence = useq.MDASequence(
    channels=["DAPI", "FITC"],
    time_plan={"interval": 0.1, "loops": 3},
)


# ------------------------------------------------------------------
# simply pass the path WITH extension
# ------------------------------------------------------------------
mmc.run_mda(sequence, writer="example.ome.zarr")

# ------------------------------------------------------------------
# or use StreamSettings for more control
# ------------------------------------------------------------------
# stream_settings = StreamSettings(root_path="example.ome.zarr", overwrite=True, asynchronous=True)  #  noqa: E501
# mmc.run_mda(sequence, writer=stream_settings)

# ------------------------------------------------------------------
# or manually create the handler and pass it to run_mda
# ------------------------------------------------------------------
# stream_settings = StreamSettings(root_path="example.ome.zarr", overwrite=True, asynchronous=True)  #  noqa: E501
# handler = OMERunnerHandler(stream_settings)
# mmc.run_mda(sequence, writer=handler)


# ------------------------------------------------------------------
# for multiple writers, pass a list of paths, settings, or handlers
# ------------------------------------------------------------------
# mmc.run_mda(sequence, writer=["example.ome.zarr", "example1.ome.zarr"])
