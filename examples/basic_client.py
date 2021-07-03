from pymmcore_plus import RemoteMMCore

with RemoteMMCore(verbose=True) as mmcore:
    # 'demo' is a special option for the included CMMCorePlus
    # that loads the micro-manager demo config
    mmcore.loadSystemConfiguration("demo")
    print("loaded:", mmcore.getLoadedDevices())
