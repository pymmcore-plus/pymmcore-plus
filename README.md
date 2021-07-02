# pymmcore-plus

Create & control [pymmcore](https://github.com/micro-manager/pymmcore) (python bindings for the C++ [micro-manager core](https://github.com/micro-manager/mmCoreAndDevices/))
running in another process.



```python
from pymmcore_plus import RemoteMMCore

with RemoteMMCore() as mmcore:
    # 'demo' is a special option for the included CMMCorePlus
    # that loads the micro-manager demo config
    mmcore.loadSystemConfiguration("demo")
    print(mmcore.getLoadedDevices())
```
