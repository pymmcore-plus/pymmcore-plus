# Multidimensional Acquisition (mda)

`pymmcore-plus` includes a basic `mda` acquisition loop {func}`~pymmcore_plus.CMMCorePlus.run_mda` that
accepts experimental sequences defined using [useq-schema](https://github.com/tlambert03/useq-schema).


```python
from useq import MDASequence, MDAEvent
import numpy as np

from pymmcore_plus import CMMCorePlus

# get the Core singleton
mmc = CMMCorePlus.instance()

# load the demo config
mmc.loadSystemConfiguration()


# Define the MDA
sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 50}],
    time_plan={"interval": 2, "loops": 5},
    z_plan={"range": 4, "step": 0.5},
    axis_order="tpcz",
)
```

There are 5 signals on the `events` object that can be used to run callbacks when mda events happen. They are:

```python
sequenceStarted = Signal(MDASequence)  # at the start of an MDA sequence
sequencePauseToggled = Signal(bool)  # when MDA is paused/unpaused
sequenceCanceled = Signal(MDASequence)  # when mda is canceled
sequenceFinished = Signal(MDASequence)  # when mda is done (whether canceled or not)
frameReady = Signal(np.ndarray, MDAEvent)  # after each event in the sequence
```

to use then connect a callback function like so:

```python
# connect as a decorator
@mmc.events.sequenceStarted.connect
def seq_started(seq: MDASequence):
    print(seq)

# or connect as an argument
def frameReady(img: np.ndarray, event: MDAEvent)
    print(img)

mmc.events.frameReady.connect(frameReady)
```


To avoid blocking further execution call `run_mda` runs on a new thread. When you first call
the method you can get a reference to the thread in case you want to do something with it.
To start the mda now call:

```python
thead = mmc.run_mda(sequence)
```


## Cancelling or Pausing

You can always pause or cancel the mda with the {func}`~pymmcore_plus.CMMCorePlus.toggle_pause`
or {func}`~pymmcore_plus.CMMCorePlus.cancel` methods.
