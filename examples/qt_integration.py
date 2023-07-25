"""
An example of integrating a MMCore object into an event loop.

This example requires qtpy and an Qt backend installed in the env:
```
pip install qtpy pyqt5
```
"""
import numpy as np
from pymmcore_plus import CMMCorePlus
from qtpy.QtWidgets import QApplication, QPushButton
from useq import MDAEvent, MDASequence

app = QApplication([])
mmcore = CMMCorePlus.instance()
stop = QPushButton("STOP")


def stop_clicked():
    mmcore.mda.cancel()
    app.quit()


stop.clicked.connect(stop_clicked)
stop.show()


# see https://github.com/pymmcore-plus/useq-schema
sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 50}],
    time_plan={"interval": 1.5, "loops": 5},
    z_plan={"range": 4, "step": 0.5},
    axis_order="tpcz",
)


@mmcore.mda.events.frameReady.connect
def on_frame(image: np.ndarray, event: MDAEvent):
    print(
        f"received frame: {image.shape}, {image.dtype} "
        f"@ index {event.index}, z={event.z_pos}"
    )


@mmcore.events.propertyChanged.connect
def prop_changed(device, prop, value):
    print(f"{device}.{prop} changed to {value!r}")


# setup some callbacks
mmcore.events.systemConfigurationLoaded.connect(lambda: print("config loaded!"))
mmcore.mda.events.sequenceFinished.connect(app.quit)

# button for early stopping

# load config and start an experiment
mmcore.loadSystemConfiguration()
mmcore.run_mda(sequence)

# start the qt event loop
app.exec_()
