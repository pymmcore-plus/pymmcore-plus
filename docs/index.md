# pymmcore-plus

`pymmcore-plus` aims to extend [pymmcore](https://github.com/micro-manager/pymmcore) (python bindings for the C++ [micro-manager core](https://github.com/micro-manager/mmCoreAndDevices/)) with a number of features designed to facilitate working with **Micro-manager in pure python/C environments**.

While you can easily use pymmcore-plus from a script or IPython/Jupyter you can also use it in combination with the [napari](https://napari.org/) based gui [napari-micromanager](https://github.com/tlambert03/napari-micromanager#napari-micromanager). See the {doc}`examples/napari-micromanager` example for how to use them together.

## Basic Usage

```python
from pymmcore_plus import CMMCorePlus
mmc = CMMCorePlus.instance()
mmc.loadSystemConfiguration() # automatically loads the demo config


print(mmc.getLoadedDevices())

# get an image as a numpy array
img = mmc.snap()
```

## Install
To install this library all you need to do is:

```bash
pip install pymmcore-plus
```

But you also need to ensure that the device adapters are present on the system. See {doc}`installing` for instructions on getting these.


```{toctree}
:maxdepth: 2

installing
contributing
API <api/pymmcore_plus>
```

```{toctree}
:caption: Examples
:maxdepth: 1

examples/mda
examples/integration-with-qt
examples/napari-micromanager
examples/context-set
```
