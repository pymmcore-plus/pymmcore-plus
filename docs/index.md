# Overview

`pymmcore-plus` aims to extend
[pymmcore](https://github.com/micro-manager/pymmcore) (python bindings for the
C++ [micro-manager core](https://github.com/micro-manager/mmCoreAndDevices/))
with a number of features designed to facilitate working with **Micro-manager in
pure python/C environments**.

![micro-manager ecosystem components](images/components.png)

## Basic Usage

```python
from pymmcore_plus import CMMCorePlus
mmc = CMMCorePlus.instance()
mmc.loadSystemConfiguration() # automatically loads the demo config


print(mmc.getLoadedDevices())

# get an image as a numpy array
img = mmc.snap()
```

While you can easily use pymmcore-plus from a script or IPython/Jupyter you can
also use it in combination with the [napari](https://napari.org/) based gui
[napari-micromanager](https://github.com/pymmcore-plus/napari-micromanager#napari-micromanager).
See [using with napari-micromanager](examples/napari-micromanager) for an
example of how to use them together.

## Install

To install this library all you need to do is:

```bash
pip install pymmcore-plus
```

But you also need to ensure that the device adapters are present on the system.
See {doc}`installing` for instructions on getting these.
