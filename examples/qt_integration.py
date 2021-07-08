"""
An example of integrating a remote MMCore object into an event loop.

This example requires qtpy and an Qt backend installed in the env:
```
pip install qtpy pyqt5
```
"""
import numpy as np
from qtpy.QtWidgets import QApplication, QPushButton
from useq import MDAEvent, MDASequence

from pymmcore_plus import RemoteMMCore

app = QApplication([])

# button for early stopping
stop = QPushButton("STOP")
stop.clicked.connect(app.quit)
stop.show()

# see https://github.com/tlambert03/useq-schema
sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 50}],
    time_plan={"interval": 1.5, "loops": 5},
    z_plan={"range": 4, "step": 0.5},
    axis_order="tpcz",
)

# start server in another process and connect to it
with RemoteMMCore() as mmcore:

    @mmcore.frameReady.connect
    def on_frame(image: np.ndarray, event: MDAEvent):
        print(
            f"received frame: {image.shape}, {image.dtype} "
            f"@ index {event.index}, z={event.z_pos}"
        )

    @mmcore.propertyChanged.connect
    def prop_changed(device, prop, value):
        print(f"{device}.{prop} changed to {value!r}")

    # setup some callbacks
    mmcore.systemConfigurationLoaded.connect(lambda: print("config loaded!"))
    mmcore.sequenceFinished.connect(app.quit)

    # load config and start an experiment
    mmcore.loadSystemConfiguration("demo")
    mmcore.run_mda(sequence)

    # start the qt event loop
    app.exec_()
