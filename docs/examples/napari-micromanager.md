# Using with napari-micromanager

If you want a nice GUI to interact with in addition to being able to script you can use [napari-micromanager](https://github.com/pymmcore-plus/napari-micromanager#napari-micromanager) which implements a GUI in [napari](https://napari.org/) using this library as a backend.


## Launching napari from a script
For complex scripting you likely will want to launch napari from a script or a jupyter notebook.

```python
from pymmcore_plus import CMMCorePlus

import napari

v = napari.Viewer()
dw, main_window = v.window.add_plugin_dock_widget("napari-micromanager")

mmc = CMMCorePlus.instance()

# do any complicated scripting you want here
...

# start napari
napari.run()
```

## Using the integrated napari terminal

After launching napari and starting the `napari-micromanager` plugin you can open the napari terminal and get a reference to the same core object that the plugin uses by running:

```python
from pymmcore_plus import CMMCorePlus

mmc = CMMCorePlus.instance()
```
