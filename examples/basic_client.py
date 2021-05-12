from pymmcore_remote import RemoteMMCore

with RemoteMMCore() as mmcore:
    # 'demo' is a special option for the included CMMCorePlus
    # that loads the micro-manager demo config
    mmcore.loadSystemConfiguration("demo")
    print("loaded:", mmcore.getLoadedDevices())
