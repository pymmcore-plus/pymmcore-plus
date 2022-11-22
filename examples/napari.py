import napari
from pymmcore_plus import CMMCorePlus

v = napari.Viewer()
dw, main_window = v.window.add_plugin_dock_widget("napari-micromanager")

# quick way to access the same core instance as napari-micromanager
mmc = CMMCorePlus.instance()

# do any complicated scripting you want here
...

# start napari
napari.run()
