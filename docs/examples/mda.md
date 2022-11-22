# Multidimensional Acquisition

`pymmcore-plus` includes a basic  Multi-dimensional Acquisition (`mda`) engine
[`CMMCorePlus.run_mda`][pymmcore_plus.CMMCorePlus.run_mda] that accepts
experimental sequences defined using
[useq-schema](https://github.com/pymmcore-plus/useq-schema).

```python linenums="1" title="run_mda.py"
--8<-- "examples/run_mda.py"
```

<!-- These comments correspond to the (1), (2) annotations in run_mda.py. -->
1. `pymmcore-plus` uses
   [`useq-schema`](https://pymmcore-plus.github.io/useq-schema/) to define
   experimental sequences.  You can either construct a [`useq.MDASequence`][]
   object manually, or
   [from a YAML/JSON file](useq-schema/#serialization-and-deserialization).
2. Access global singleton:
   [`CMMCorePlus.instance`][pymmcore_plus.CMMCorePlus.instance]
3. See
   [`CMMCorePlus.loadSystemConfiguration`][pymmcore_plus.CMMCorePlus.loadSystemConfiguration]
4. For info on all of the signals available to connect to, see the
    [MDA Events API][pymmcore_plus.mda.events.PMDASignaler]
5. To avoid blocking further execution,
    [`run_mda`][pymmcore_plus.CMMCorePlus.run_mda] runs on a new thread.
    (`run_mda` returns a reference to the thread in case you want to do
    something with it, such as wait for it to finish with
    [threading.Thread.join][])

## Cancelling or Pausing

You can pause or cancel the mda with the
[`CMMCorePlus.mda.toggle_pause`][pymmcore_plus.mda._runner.MDARunner.toggle_pause]
or [`CMMCorePlus.mda.cancel`][pymmcore_plus.mda._runner.MDARunner.cancel]
methods.

## Registering a new MDA Engine

By default the built-in [`MDAEngine`][pymmcore_plus.mda.MDAEngine] will be used
to run the MDA. However, you can create a custom acquisition engine and register
it use
[`CMMCorePlus.register_mda_engine`][pymmcore_plus.CMMCorePlus.register_mda_engine].

Your engine must conform to the engine protocol defined by
[`pymmcore_plus.mda.PMDAEngine`][]. To ensure that your engine conforms you can
inherit from the protocol.

You can be alerted to the the registering of a new engine with the
[`core.events.mdaEngineRegistered`][pymmcore_plus.core.events._protocol.PCoreSignaler.mdaEngineRegistered]
signal.

```python
@mmc.events.mdaEngineRegistered
def new_engine(new_engine, old_engine):
    print('new engine registered!")
```
