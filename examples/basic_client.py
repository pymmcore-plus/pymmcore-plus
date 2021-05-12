from pymmcore_remote import RemoteMMCore

with RemoteMMCore() as mmcore:
    mmcore.loadSystemConfiguration("demo")  # 'demo' is a special option for CMMCorePlus
    print("loaded:", mmcore.getLoadedDevices())
