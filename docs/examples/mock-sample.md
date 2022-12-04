# Mock sample data

The [pymmcore_plus.mock_sample][] decorator lets you define a function that
generates mock data each time the underlying `core.getImage` function is
called. This may be useful for testing purposes, or for generating mock data
for a demo.

```python linenums="1" title="mock_sample.py"
--8<-- "examples/mock_sample.py"
```

<!-- These comments correspond to the (1), (2) annotations in mock_sample.py. -->
1. If you don't pass an `mmcore` argument, it will use the global
    [`CMMCorePlus.instance`][pymmcore_plus.CMMCorePlus.instance]. By default, it
    will loop forever, restarting the generator when it finishes, but you can
    pass `loop=False` if you prefer, in which case a `StopIteration` exception
    will be raised when the generator finishes.
2. prints `(512, 512)` for the demo camera (or whatever the current camera ROI
    size is)
3. Within this context whenever
    [core.getImage][pymmcore_plus.CMMCorePlus.getImage] is called, it will
    return the next image yielded by the mock_sample-decorated generator
    function.
4. prints `(10, 10)` (since that's what we passed to `noisy_sample`).
5. prints `(512, 512)` again now that the context is exited (or whatever the
    current camera ROI size is)
