# Migrating from Pycro-manager

## Pycro-manager

[Pycro-manager](https://github.com/micro-manager/pycro-manager) is a python
library that allows control of the Java Micro-manager application using python.
It works by communicating with micro-manager running in another process
via a ZMQ socket. Commands are serialized and sent to the Java process, which
in turn controls the native C++ micro-manager core via MMCoreJ.

This has the advantage of being able to use all existing Java-based
micro-manager plugins and libraries. But the design also comes with
some limitations:

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
  pymmcore-widgets](https://pymmcore-plus.github.io/pymmcore-widgets/widgets/ImagePreview/)

It does _not_ reimplement the fast Java-based
[ANDTiffStorage](https://github.com/micro-manager/NDTiffStorage) file format.
However, we would prefer to see time invested in a
[zarr](https://github.com/zarr-developers/zarr-python)-writer instead, perhaps
leveraging the recently developed [acquire
project](https://github.com/acquire-project/acquire-python)

## API Migration Guide

### `Acquisition.acquire` &rarr; `CMMCorePlus.run_mda`

`pycromanager`'s [`Acquisition`
class](https://pycro-manager.readthedocs.io/en/latest/acq_overview.html)
executes a sequence of acquisition events. The equivalent in `pymmcore-plus` is
the `CMMCorePlus.run_mda` method. (Note that saving to disk is not currently
handled by `run_mda` itself, and must be handled separately)

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

Just [as in pycromanager](https://pycro-manager.readthedocs.io/en/latest/acq_overview.html#hardware-sequencing), the `pymmcore-plus` supports hardware sequencing, but
you must [enable it explicitly](mda_engine.md#hardware-triggered-sequences).

### `multi_d_acquisition_events` &rarr; `useq.MDASequence`

In `pycromanager`, the
[`multi_d_acquisition_events`](https://pycro-manager.readthedocs.io/en/latest/apis.html#pycromanager.multi_d_acquisition_events)
function is used to generate event `dicts` for a typical multi-dimensional
acquisition. In `pymmcore-plus`, the [`useq.MDASequence`][] class from the
`useq-schema` library accomplishes a similar goal.

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

`pycromanager` introduced the concept of [acquisition hooks](
https://pycro-manager.readthedocs.io/en/latest/acq_hooks.html#acq-hooks) to enable
users to customize the behavior of the acquisition engine.  This allowed execution
of python functions at various points in the acquisition process, in order to
drive hardware outside of the core micro-manager API, or to modify/delete events
in progress.

`pymmcore-plus` also allows customization of the acquisition process, but 