# Migrating from Pycro-manager

This page summarizes some of the differences between `pycromanager` and
`pymmcore-plus`, and provides some guidance for migrating from one to the other.

!!! info "See also..."

    The [pycromanager-like API example](../examples/pycro-manager-api.md) as
    an educational example of how a pycro-manager Aquistion class would be
    re-implemented on pymmcore-plus.
 
## Pycro-manager

[Pycro-manager](https://github.com/micro-manager/pycro-manager) is a python
library that allows control of the Java Micro-manager application using python.
It works by communicating with micro-manager running in another process
via a ZMQ socket. Commands are serialized and sent to the Java process, which
in turn controls the native C++ micro-manager core via MMCoreJ.

This has the advantage of being able to use the mature MMStudio ecosystem, and
all existing Java-based micro-manager plugins and libraries. But the design also
comes with some limitations:

- it requires Java be installed and running, which makes installation and
  startup more complicated.
- the ZMQ bridge has a [speed limit of ~100
  MB/s](https://pycro-manager.readthedocs.io/en/latest/performance_guide.html),
  meaning that data-intensive applications cannot stream data directly to Python
  without saving to disk first. This limits the scope of what python-based
  online image processing can do.
- `pycromanager` calls to MMCore have more overhead than calls
  directly to pymmcore. This is because they need to first travel through
  the python-Java ZeroMQ bridge before going to the core (and then again
  to get back to python). This can result in calls to core being a couple
  of orders of magnitude slower than direct calls to pymmcore.
- Calling arbitrary python code from Java can be difficult. `pycromanager`
  provides "hooks" for passing specific functions to be called during
  acquisition, but it's not a general solution.

## pymmcore-plus

`pymmcore-plus` and related libraries attempts to remove Java from the equation
by reimplementing the core functionality of micro-manager and MMStudio in python. It is built on top of [`pymmcore`](https://github.com/micro-manager/pymmcore), which provides direct access to the C++ core via a SWIG interface.

This includes:

- a pure python [Acquisition engine](./mda_engine.md) that replaces the legacy [clojure
  acqEngine](https://github.com/micro-manager/micro-manager/tree/main/acqEngine/src/main/clj/org/micromanager)
  and the newer [Java AcqEngJ](https://github.com/micro-manager/AcqEngJ)
- [pymmcore-widgets](https://pymmcore-plus.github.io/pymmcore-widgets): a set of Qt-based GUI widgets that aim to replace the Java-based [MMStudio
  GUI](https://github.com/micro-manager/micro-manager)
- integration with the python image viewer [napari](https://napari.org/) via
  [napari-micromanager](https://github.com/pymmcore-plus/napari-micromanager).
  (Or, if you simply want image-preview without 3D features, you might have
  better performance with the [image-preview widget in
  pymmcore-widgets](https://pymmcore-plus.github.io/pymmcore-widgets/widgets/ImagePreview/))

It does _not_ reimplement the fast Java-based
[ANDTiffStorage](https://github.com/micro-manager/NDTiffStorage) file format.
We would like to see time invested in a
[zarr](https://github.com/zarr-developers/zarr-python)-writer instead, perhaps
leveraging the recently developed [acquire
project](https://github.com/acquire-project/acquire-python).

!!! warning "Reasons *not* to migrate"

    If the majority of your acquisition/analysis code is written in python,
    or if you'd like to remove Java and inter-process communication from your
    workflow, then `pymmcore` and `pymmcore-plus` have a lot to offer.
    But you should be aware of what you're giving up:

    - The Java-based micro-manager ecosystem is mature and stable.
      It has been tested over many years and is used in many labs. While
      `pymmcore` is also mature and stable, `pymmcore-plus` is relatively
      new (though, extensively tested.)
    - Many end-users are familiar with the Java MMStudio GUI, and there are many
      plugins and libraries built around it. `napari-micromanager` and
      `pymmcore-widgets` are comparatively much newer and less mature.
    - There are ready-built solutions for file I/O and data storage
      in the Java-based micro-manager (such as `ANDTiffStorage``).
      `pymmcore-plus` users will currently need to design their own
      data-saving solutions (this is a work in progress).

## API Migration Guide

### `Acquisition.acquire` &rarr; `CMMCorePlus.run_mda`

`pycromanager`'s [`Acquisition`
class](https://pycro-manager.readthedocs.io/en/latest/acq_overview.html)
executes a sequence of acquisition events. The equivalent in `pymmcore-plus` is
the `CMMCorePlus.run_mda` method.

> :exclamation: **Note**: saving to disk is not currently
handled by `run_mda` itself, and must be implemented separately.  So there
is no equivalent of `directory` and `name` arguments.

!!! note "pycromanager"

    After launching the micro-manager GUI, or starting a headless
    process, you run an acquisition in `pycromanager` like this:

    ```python
    from pycromanager import Acquisition

    with Acquisition(...) as acq:
        events = [...]  # list of events
        acq.acquire(events)
    ```
    ... where `events` is a list of `dict` objects in the
    [pycro-manager event format](https://pycro-manager.readthedocs.io/en/latest/apis.html#acquisition-event-specification)

!!! note "pymmcore-plus"

    In `pymmcore-plus``, you directly instantiate the MMCore instance, and then use the
    [`run_mda`][pymmcore_plus.CMMCorePlus.run_mda] method to execute a sequence of
    events (See [The Acquisition Engine](./mda_engine.md) for more details)

    ```python
    from pymmcore_plus import CMMCorePlus

    core = CMMCorePlus()
    events = [...]  # list of events
    core.run_mda(events)
    ```

    ... where `events` is any iterable of [`useq.MDAEvent`][] objects.

Just [as in
pycromanager](https://pycro-manager.readthedocs.io/en/latest/acq_overview.html#hardware-sequencing),
the `pymmcore-plus` supports [hardware
sequencing](https://micro-manager.org/Hardware-based_Synchronization_in_Micro-Manager),
but you must [enable it explicitly](mda_engine.md#hardware-triggered-sequences).

```python
core = CMMCorePlus()
# enable hardware triggering
core.mda.engine.use_hardware_sequencing = True
```

### `multi_d_acquisition_events` &rarr; `useq.MDASequence`

In `pycromanager`, the
[`multi_d_acquisition_events`](https://pycro-manager.readthedocs.io/en/latest/apis.html#pycromanager.multi_d_acquisition_events)
function is used to generate event `dicts` for a typical multi-dimensional
acquisition. 

!!! note "pycromanager"

    ```python
    from pycromanager import multi_d_acquisition_events

    events = multi_d_acquisition_events(
        num_time_points=4,
        time_interval_s=0.5,
        channel_group="Channel",
        channels=["DAPI", "FITC"],
        z_start=0,
        z_end=6,
        z_step=0.4,
        order="tcz",
    )
    ```

In `pymmcore-plus`, the [`useq.MDASequence`][] class from the `useq-schema`
library accomplishes a similar goal.

!!! note "pymmcore-plus"

    ```python
    from useq import MDASequence

    events = MDASequence(
        time_plan={'loops': 4, 'interval': 0.5},
        channels=["DAPI", "FITC"], # (1)!
        z_plan={'bottom': 0, 'top': 6, 'step': 0.4},
        axis_order="tcz",
    )
    ```

    1. Config group `"Channel"` is the default in `pymmcore-plus`, so you don't
       need to specify it explicitly.  But if you need to specify a group, you
       can use
       `channels=[{"group": "Channel", "config": "DAPI"},  ...]`

`MDASequence` has *many* additional features and ways to express an MDA, including
nested, position-specific sequences, channel-based time or Z-stack skipping, and more.
See the [useq-schema docs](https://pymmcore-plus.github.io/useq-schema/schema/sequence/)
for more details.

### Acquisition-hooks &rarr; `useq.MDAHooks`

`pycromanager` introduced the concept of [acquisition hooks](https://pycro-manager.readthedocs.io/en/latest/acq_hooks.html#acq-hooks) to enable
users to customize the behavior of the acquisition engine. This allowed execution
of python functions at various points in the acquisition process, in order to
drive hardware outside of the core micro-manager API, or to modify/delete events
in progress.

`pymmcore-plus` also allows customization of the acquisition process, but not
via hooks. Because `pymmcore-plus` doesn't need to communicate with a Java
acquisition engine over a ZMQ socket, it is possible to directly subclass the
[`MDAEngine`][pymmcore_plus.mda.MDAEngine] class, and override/extend its
methods to customize the acquisition process.

- `event_generation_hook_fn` &rarr;
  [`MDAEngine.event_iterator`][pymmcore_plus.mda.PMDAEngine.event_iterator].  
  (See also [Event-Driven Acquisition](mda_engine.md#event-driven-acquisition)
  for powerful ways to modify/extend the event iteration process.)
- `pre_hardware_hook_fn` &rarr; [`MDAEngine.setup_event`][pymmcore_plus.mda.PMDAEngine.setup_event]
  (before `super()`)
- `post_hardware_hook_fn` &rarr; [`MDAEngine.setup_event`][pymmcore_plus.mda.PMDAEngine.setup_event]
  (after `super()`)
- `post_camera_hook_fn` &rarr; [`MDAEngine.exec_event`][pymmcore_plus.mda.PMDAEngine.exec_event]
  (after `super()`)
- `image_process_fn` &rarr;
  [`mda.events.frameReady.connect`](mda_engine.md#handling-acquired-data)
- `image_saved_fn` &rarr; There is no direct equivalent to this hook in
  `pymmcore-plus`, because the `MDAEngine` class doesn't directly handle saving data.
  (It's also less necessary because of the lack of a ZMQ socket means you can immediately
  process data in the python process that is running the acquisition.)

!!! note "pycromanager"

    ```python
    from pycromanager import Acquisition

    def my_event_generation_hook_fn(event, event_queue):
        ...

    def my_pre_hardware_hook_fn(event, event_queue):
        ...

    def my_post_hardware_hook_fn(event, event_queue):
        ...

    def my_post_camera_hook_fn(event, event_queue):
        ...

    def my_image_process_fn(image, metadata, event_queue):
        ...

    def my_image_saved_fn(axes, dataset, event_queue):
        ...

    with Acquisition(
        event_generation_hook_fn=my_event_generation_hook_fn,
        pre_hardware_hook_fn=my_pre_hardware_hook_fn,
        post_hardware_hook_fn=my_post_hardware_hook_fn,
        post_camera_hook_fn=my_post_camera_hook_fn,
        image_process_fn=my_image_process_fn,
        image_saved_fn=my_image_saved_fn,
    ):
        ...
    ```

!!! note "pymmcore-plus"

    ```python
    from typing import Iterable, Iterator
    from pymmcore_plus import CMMCorePlus
    from pymmcore_plus.mda import MDAEngine
    import useq

    class MyEngine(MDAEngine):

        def event_iterator(self, events: Iterable[useq.MDAEvent]) -> Iterator[useq.MDAEvent]:
            # anything you might do in event_generation_hook_fn(), and more
            yield from events  # default implementation

        def setup_event(self, event: useq.MDAEvent) -> None:
            # pre_hardware_hook_fn()
            super().setup_event(event)
            # post_hardware_hook_fn()

        def exec_event(self, event: useq.MDAEvent) -> object:
            # do some custom pre-execution
            result = super().exec_event(event)
            # my_post_camera_hook_fn() ... or implement `self.teardown_event()`
            return result

        # -------- advanced ----------

        def exec_sequenced_event(self, event: SequencedEvent) -> object:
            # do some custom pre-sequence-acquisition
            result = super().exec_sequenced_event(event)
            # do some custom post-sequence-acquisition
            return result

    core = CMMCorePlus.instance()
    core.loadSystemConfiguration()

    # Register the custom engine with the runner
    core.mda.set_engine(MyEngine(core))
    ```

See [Customizing the Acquisition Engine](custom_engine.md) for more details.

### Low-level MMCore control

Direct control of the MMCore object is one of the main strengths of `pymmcore[-plus]`.

In pycromanager, if you want to control the MMCore object, you can
get a ZMQ bridge to it via `pycromanager.Core()`.

!!! note "pycromanager"

    ```python
    from pycromanager import Core

    # get ZMQ-bridge to Java MMCore
    core = Core()

    #### Calling core functions ###
    exposure = core.get_exposure()
    ```

In `pymmcore-plus` you just directly instantiate and use the `CMMCorePlus`
class. (Note, `pymmcore-plus` does _not_ convert all `camelCase` functions to
`snake_case`.) Because of type-stubs that were upstreamed to `pymmcore`, you
will get autocomplete and intellisense for all CMMCore methods, making
development easier.

!!! note "pymmcore-plus"

    ```python
    from pymmcore_plus import CMMCorePlus

    # get MMCorePlus object
    core = CMMCorePlus()
    # OR, for easy access to the singleton instance
    core = CMMCorePlus.instance()

    # because you're creating it here, rather than connecting
    # to an existing micro-manager application,
    # you'll likely want to load the system configuration
    core.loadSystemConfiguration()

    #### Calling core functions ###
    exposure = core.getExposure()
    ```

This is one place where using `pymmcore[-plus]` directly really shines. All
core calls will be significantly faster, because they don't need to
be sent back and forth over a ZMQ socket.

!!! tip "Speed comparison"

    (with `pycromanager` v0.28.1 and `pymmcore-plus` v0.8.0)

    ```python
    In [1]: from pycromanager import Core

    In [2]: core = Core()

    In [3]: %timeit core.get_exposure()
    158 µs ± 10.1 µs per loop (mean ± std. dev. of 7 runs, 10,000 loops each)

    In [4]: from pymmcore_plus import CMMCorePlus

    In [5]: core_plus = CMMCorePlus()

    In [6]: core_plus.loadSystemConfiguration()

    In [7]: %timeit core_plus.getExposure()
    511 ns ± 4.78 ns per loop (mean ± std. dev. of 7 runs, 1,000,000 loops each)  # (1)!
    ```

    1. :fire: ~300x faster!
