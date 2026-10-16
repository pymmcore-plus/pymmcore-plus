# Set as a Context

You may want to temporarily set something on core such as
`core.setAutoShutter(False)` when writing an MDA Engine. For this case you can
use the convenience method
[`CMMCorePlus.setContext`][pymmcore_plus.CMMCorePlus.setContext].

```python linenums="1" title="set_as_context.py"
--8<-- "examples/set_as_context.py"
```

This will work for the `set` methods on the core such as
[`setAutoShutter`][pymmcore_plus.CMMCorePlus.setAutoShutter],
[`setShutterOpen`][pymmcore_plus.CMMCorePlus.setShutterOpen], ...
