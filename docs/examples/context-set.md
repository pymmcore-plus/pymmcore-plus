# Set as a Context

You may want to temporarily set something on core such as  `core.setAutoShutter(False)` when writing an MDA Engine. For this case
you can use the convenience method [`pymmcore_plus.CMMCorePlus.setContext`][].

```python
from pymmcore_plus import CMMCorePlus
core = CMMCorePlus.instance()
with core.setContext(autoShutter = False):
    assert not core.getAutoShutter()
    # do other stuff

assert core.getAutoShutter()
```

This will work for the `set` methods on the core such as `setAutoShutter`, `setShutterOpen`, ...
