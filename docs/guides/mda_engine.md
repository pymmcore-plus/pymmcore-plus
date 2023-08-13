# The Acquisition Engine

One of the key features of the pymmcore-plus is the python acquisition engine.
This allows you to define and execute a sequence of events (without relying on
Java). The sequence may be a typical multi-dimensional acquisition (MDA), such
as a z-stack across multiple channels, stage positions, and time points, or it
can be any custom sequence of events that you define. It needn't even be a
sequence of known length: you can define an iterable or a [`queue.Queue`][] of
events that reacts to the results of previous events, for event-driven "smart"
microscopy.

The built-in acquisition engine will support many standard use-cases, but you
can also subclass and customize it, allowing arbitrary python code to be
executed at each step of the acquisition. This makes it possible to incorporate
custom hardware control (e.g. to control devices for which micro-manager has no
adapters), data analysis, or other logic into the experiment.

## Running a very simple sequence

To execute a sequence, you must:

1. Create a [`CMMCorePlus`][pymmcore_plus.CMMCorePlus] instance (and probably load a
   configuration file)
2. Pass an iterable of [`useq.MDAEvent`][] objects to the [`run_mda()`][pymmcore_plus.CMMCorePlus.run_mda] method.

```python
from pymmcore_plus import CMMCorePlus
from useq import MDAEvent

# Create the core instance.
mmc = CMMCorePlus.instance()  # (1)!
mmc.loadSystemConfiguration()  # (2)!

# Create a super-simple sequence, with one event
mda_sequence = [MDAEvent()] # (3)!

# Run it!
mmc.run_mda(mda_sequence)
```

1. Here, we use the global
   [`CMMCorePlus.instance`][pymmcore_plus.CMMCorePlus.instance] singleton.
2. This loads the demo configuration by default. Pass in your own config file.
   See
   [`CMMCorePlus.loadSystemConfiguration`][pymmcore_plus.CMMCorePlus.loadSystemConfiguration]
3. An experiment is just an iterable of [`useq.MDAEvent`][] objects.

!!! Tip

    [`CMMCorePlus.run_mda`][pymmcore_plus.CMMCorePlus.run_mda] is
    a convenience method that runs the experiment in a separate thread. If you
    want to run it in the main thread, use
    [`CMMCorePlus.mda.run`][pymmcore_plus.mda.MDARunner.run] directly.

    ```py
    mmc.mda.run(seq)
    ```

The code above will execute a single, very boring event! It will snap
one image (the default action of an `MDAEvent`) with the current exposure
time, channel, stage position, etc... and then stop.

Let's make it a little more interesting.

## The `MDAEvent` object

The [`useq.MDAEvent`][] object is the basic building block of an experiment. It
is a relatively simple dataclass that defines a single action to be performed.
For complete details, see the [useq-schema
documentation](https://pymmcore-plus.github.io/useq-schema/schema/event/), but
some key attributes you might want to set are:

- **exposure** (`float`): The exposure time (in milliseconds) to use for this
  event.
- **channel** (`str | dict[str, str]`): The configuration group to use. If a
  `dict`, it should have two keys: `group` and `config` (the configuration group
  and preset, respectively). If a `str`, it is assumed to be the name of a preset in
  the `Channel` group.
- **x_pos**, **y_pos**, **z_pos** (`float`): An `x`, `y`, and `z` stage position
  to use for this event.
- **min_start_time** (`float`): The minimum time to wait before starting this
  event.(in seconds, relative to the start of the experiment)

!!! example

    ```python
    snap_a_dapi = MDAEvent(channel="DAPI", exposure=100, x_pos=1100, y_pos=1240)
    ```

    **NOTE:** The name `"DAPI"` here must be a name of a
    [preset](https://micro-manager.org/Micro-Manager_Configuration_Guide#configuration-presets)
    in your micro-manager "Channel" configuration group.

For any missing keys, the implied meaning is "use the current setting". For
example, an `MDAEvent` without an `x_pos` or a `y_pos` will use the current
stage position.

The implied "action" of an `MDAEvent` is to snap an image. But there are ways to
customize that, described later.

## A multi-event sequence

With our understanding of `MDAEvent` objects, we can now create a slightly more
interesting experiment. This one will snap four images: two channels at two
different stage positions.

```python
from pymmcore_plus import CMMCorePlus
from useq import MDAEvent

# Create the core instance.
mmc = CMMCorePlus.instance()
mmc.loadSystemConfiguration()

# Snap two channels at two positions
mda_sequence = [
    MDAEvent(channel={'config': "DAPI"}, x_pos=1100, y_pos=1240),
    MDAEvent(channel={'config': "FITC"}, x_pos=1100, y_pos=1240),
    MDAEvent(channel={'config': "DAPI"}, x_pos=1442, y_pos=1099),
    MDAEvent(channel={'config': "FITC"}, x_pos=1442, y_pos=1099),
]

# Run it!
mmc.run_mda(mda_sequence)
```

!!! info "Logs"

    If you run the code above, you will see some logs printed to the console
    that look something like this:

    ```log
    2023-08-12 16:37:50,694 - INFO - MDA Started: GeneratorMDASequence()
    2023-08-12 16:37:50,695 - INFO - channel=Channel(config='DAPI') x_pos=1100.0 y_pos=1240.0
    2023-08-12 16:37:50,881 - INFO - channel=Channel(config='FITC') x_pos=1100.0 y_pos=1240.0
    2023-08-12 16:37:50,891 - INFO - channel=Channel(config='DAPI') x_pos=1442.0 y_pos=1099.0
    2023-08-12 16:37:50,947 - INFO - channel=Channel(config='FITC') x_pos=1442.0 y_pos=1099.0
    2023-08-12 16:37:50,958 - INFO - MDA Finished: GeneratorMDASequence()
    ```

    See [logging](logging.md) for more details on how to configure and review logs.

At this point, you might thinking that constructing a sequence by hand is a
little tedious. And you'd be right! That's why we have the
`MDASequence` class.

## Building sequences with `MDASequence`

For most standard multi-dimensional experiments, you will want to use
[`useq.MDASequence`][] to construct your sequence of events. It allows you to
declare a plan for each axis in your experiment (channels, time, z, etc...)
along with the order in which the axes should be iterated.

See the [useq-schema documentation](https://pymmcore-plus.github.io/useq-schema/schema/sequence/)
for complete details, but let's look at how `MDASequence` can be used to
create a few common experiments.

### A two-channel time series

```python
from useq import MDASequence

mda_sequence = MDASequence(
    time_plan={"interval": 2, "loops": 6}, # (1)!
    channels=[
        {"config": "DAPI", "exposure": 50},
        {"config": "FITC", "exposure": 80},
    ]
)
```

1. 10 loops, with a 2 second interval between each loop. See also, [additional
   time-plans](https://pymmcore-plus.github.io/useq-schema/schema/axes/#time-plans).

??? example "output of `list(mda_sequence)`"

    ```python
    [
        MDAEvent(index={'t': 0, 'c': 0}, channel=Channel(config='DAPI'), exposure=50.0, min_start_time=0.0),
        MDAEvent(index={'t': 0, 'c': 1}, channel=Channel(config='FITC'), exposure=80.0, min_start_time=0.0),
        MDAEvent(index={'t': 1, 'c': 0}, channel=Channel(config='DAPI'), exposure=50.0, min_start_time=2.0),
        MDAEvent(index={'t': 1, 'c': 1}, channel=Channel(config='FITC'), exposure=80.0, min_start_time=2.0),
        MDAEvent(index={'t': 2, 'c': 0}, channel=Channel(config='DAPI'), exposure=50.0, min_start_time=4.0),
        MDAEvent(index={'t': 2, 'c': 1}, channel=Channel(config='FITC'), exposure=80.0, min_start_time=4.0),
        MDAEvent(index={'t': 3, 'c': 0}, channel=Channel(config='DAPI'), exposure=50.0, min_start_time=6.0),
        MDAEvent(index={'t': 3, 'c': 1}, channel=Channel(config='FITC'), exposure=80.0, min_start_time=6.0),
        MDAEvent(index={'t': 4, 'c': 0}, channel=Channel(config='DAPI'), exposure=50.0, min_start_time=8.0),
        MDAEvent(index={'t': 4, 'c': 1}, channel=Channel(config='FITC'), exposure=80.0, min_start_time=8.0),
        MDAEvent(index={'t': 5, 'c': 0}, channel=Channel(config='DAPI'), exposure=50.0, min_start_time=10.0),
        MDAEvent(index={'t': 5, 'c': 1}, channel=Channel(config='FITC'), exposure=80.0, min_start_time=10.0),
    ]
    ```

### A Z-stack at three positions

```python
from useq import MDASequence, Position

mda_sequence = MDASequence(
    z_plan={"range": 4, "step": 0.5},  # (1)!
    stage_positions=[  # (2)!
        (10, 10, 20),
        {'x': 30, 'y': 40, 'z': 50},
        Position(x=60, y=70, z=80),
    ]
)
```

1. A 4-micron Z-stack with 0.5 micron steps, ranging around each position. See
   also, [additional
   z-plans](https://pymmcore-plus.github.io/useq-schema/schema/axes/#z-plans).
2. These are all valid ways to specify a [stage
   position](https://pymmcore-plus.github.io/useq-schema/schema/axes/#useq.Position).
   None of `x`, `y`, or `z` are required.

??? example "output of `list(mda_sequence)`"

    ```python
    [
        MDAEvent(index={'p': 0, 'z': 0}, x_pos=10.0, y_pos=10.0, z_pos=18.0),
        MDAEvent(index={'p': 0, 'z': 1}, x_pos=10.0, y_pos=10.0, z_pos=18.5),
        MDAEvent(index={'p': 0, 'z': 2}, x_pos=10.0, y_pos=10.0, z_pos=19.0),
        MDAEvent(index={'p': 0, 'z': 3}, x_pos=10.0, y_pos=10.0, z_pos=19.5),
        MDAEvent(index={'p': 0, 'z': 4}, x_pos=10.0, y_pos=10.0, z_pos=20.0),
        MDAEvent(index={'p': 0, 'z': 5}, x_pos=10.0, y_pos=10.0, z_pos=20.5),
        MDAEvent(index={'p': 0, 'z': 6}, x_pos=10.0, y_pos=10.0, z_pos=21.0),
        MDAEvent(index={'p': 0, 'z': 7}, x_pos=10.0, y_pos=10.0, z_pos=21.5),
        MDAEvent(index={'p': 0, 'z': 8}, x_pos=10.0, y_pos=10.0, z_pos=22.0),
        MDAEvent(index={'p': 1, 'z': 0}, x_pos=30.0, y_pos=40.0, z_pos=48.0),
        MDAEvent(index={'p': 1, 'z': 1}, x_pos=30.0, y_pos=40.0, z_pos=48.5),
        MDAEvent(index={'p': 1, 'z': 2}, x_pos=30.0, y_pos=40.0, z_pos=49.0),
        MDAEvent(index={'p': 1, 'z': 3}, x_pos=30.0, y_pos=40.0, z_pos=49.5),
        MDAEvent(index={'p': 1, 'z': 4}, x_pos=30.0, y_pos=40.0, z_pos=50.0),
        MDAEvent(index={'p': 1, 'z': 5}, x_pos=30.0, y_pos=40.0, z_pos=50.5),
        MDAEvent(index={'p': 1, 'z': 6}, x_pos=30.0, y_pos=40.0, z_pos=51.0),
        MDAEvent(index={'p': 1, 'z': 7}, x_pos=30.0, y_pos=40.0, z_pos=51.5),
        MDAEvent(index={'p': 1, 'z': 8}, x_pos=30.0, y_pos=40.0, z_pos=52.0),
        MDAEvent(index={'p': 2, 'z': 0}, x_pos=60.0, y_pos=70.0, z_pos=78.0),
        MDAEvent(index={'p': 2, 'z': 1}, x_pos=60.0, y_pos=70.0, z_pos=78.5),
        MDAEvent(index={'p': 2, 'z': 2}, x_pos=60.0, y_pos=70.0, z_pos=79.0),
        MDAEvent(index={'p': 2, 'z': 3}, x_pos=60.0, y_pos=70.0, z_pos=79.5),
        MDAEvent(index={'p': 2, 'z': 4}, x_pos=60.0, y_pos=70.0, z_pos=80.0),
        MDAEvent(index={'p': 2, 'z': 5}, x_pos=60.0, y_pos=70.0, z_pos=80.5),
        MDAEvent(index={'p': 2, 'z': 6}, x_pos=60.0, y_pos=70.0, z_pos=81.0),
        MDAEvent(index={'p': 2, 'z': 7}, x_pos=60.0, y_pos=70.0, z_pos=81.5),
        MDAEvent(index={'p': 2, 'z': 8}, x_pos=60.0, y_pos=70.0, z_pos=82.0)
    ]
    ```

### A grid of Z-stacks

Here we use `axis_order` to declare that we want the full Z-stack
to happen at each `(row, col)` before moving to the next
position in the grid.

```python
from useq import MDASequence

mda_sequence = MDASequence(
    stage_positions=[{'x': 100, 'y': 200, 'z': 300}],
    grid_plan={"fov_width": 20, "fov_height": 10, "rows": 2, "columns": 2},
    z_plan={"range": 10, "step": 2.5},
    axis_order="pgz"  # (1)!
)
```

1.  The "fastest" axes come last. By putting `z` after `g` in the `axis_order`,
    we're saying "at each `g`, do a full `z` iteration".

??? example "output of `list(mda_sequence)`"

    ```python
    [
        MDAEvent(index={'p': 0, 'g': 0, 'z': 0}, x_pos=90.0, y_pos=205.0, z_pos=295.0),
        MDAEvent(index={'p': 0, 'g': 0, 'z': 1}, x_pos=90.0, y_pos=205.0, z_pos=297.5),
        MDAEvent(index={'p': 0, 'g': 0, 'z': 2}, x_pos=90.0, y_pos=205.0, z_pos=300.0),
        MDAEvent(index={'p': 0, 'g': 0, 'z': 3}, x_pos=90.0, y_pos=205.0, z_pos=302.5),
        MDAEvent(index={'p': 0, 'g': 0, 'z': 4}, x_pos=90.0, y_pos=205.0, z_pos=305.0),
        MDAEvent(index={'p': 0, 'g': 1, 'z': 0}, x_pos=110.0, y_pos=205.0, z_pos=295.0),
        MDAEvent(index={'p': 0, 'g': 1, 'z': 1}, x_pos=110.0, y_pos=205.0, z_pos=297.5),
        MDAEvent(index={'p': 0, 'g': 1, 'z': 2}, x_pos=110.0, y_pos=205.0, z_pos=300.0),
        MDAEvent(index={'p': 0, 'g': 1, 'z': 3}, x_pos=110.0, y_pos=205.0, z_pos=302.5),
        MDAEvent(index={'p': 0, 'g': 1, 'z': 4}, x_pos=110.0, y_pos=205.0, z_pos=305.0),
        MDAEvent(index={'p': 0, 'g': 2, 'z': 0}, x_pos=110.0, y_pos=195.0, z_pos=295.0),
        MDAEvent(index={'p': 0, 'g': 2, 'z': 1}, x_pos=110.0, y_pos=195.0, z_pos=297.5),
        MDAEvent(index={'p': 0, 'g': 2, 'z': 2}, x_pos=110.0, y_pos=195.0, z_pos=300.0),
        MDAEvent(index={'p': 0, 'g': 2, 'z': 3}, x_pos=110.0, y_pos=195.0, z_pos=302.5),
        MDAEvent(index={'p': 0, 'g': 2, 'z': 4}, x_pos=110.0, y_pos=195.0, z_pos=305.0),
        MDAEvent(index={'p': 0, 'g': 3, 'z': 0}, x_pos=90.0, y_pos=195.0, z_pos=295.0),
        MDAEvent(index={'p': 0, 'g': 3, 'z': 1}, x_pos=90.0, y_pos=195.0, z_pos=297.5),
        MDAEvent(index={'p': 0, 'g': 3, 'z': 2}, x_pos=90.0, y_pos=195.0, z_pos=300.0),
        MDAEvent(index={'p': 0, 'g': 3, 'z': 3}, x_pos=90.0, y_pos=195.0, z_pos=302.5),
        MDAEvent(index={'p': 0, 'g': 3, 'z': 4}, x_pos=90.0, y_pos=195.0, z_pos=305.0)
    ]
    ```

### Skip timepoints or Z-stacks

The [`Channel` field](https://pymmcore-plus.github.io/useq-schema/schema/axes/#useq.Channel)
has a few tricks, such as skipping timepoints or Z-stacks for specific channels.
Here we take a fast Z-stack (leaving the shutter open) in the `FITC` channel only, and
a single image in the `DIC` channel every 3 timepoints:

```python
from useq import MDASequence

mda_sequence = MDASequence(
    z_plan={"range": 10, "step": 2.5},
    time_plan={"interval": 2, "loops": 6},
    channels=[
        "FITC",
        {"config": "DIC", "acquire_every": 3, "do_stack": False},
    ],
    keep_shutter_open_across=['z'],
)
```

??? example "output of `list(mda_sequence)`"

    ```python
    [
        MDAEvent(index={'t': 0, 'c': 0, 'z': 0}, channel='FITC', min_start_time=0.0, z_pos=-5.0, keep_shutter_open=True),
        MDAEvent(index={'t': 0, 'c': 0, 'z': 1}, channel='FITC', min_start_time=0.0, z_pos=-2.5, keep_shutter_open=True),
        MDAEvent(index={'t': 0, 'c': 0, 'z': 2}, channel='FITC', min_start_time=0.0, z_pos=0.0, keep_shutter_open=True),
        MDAEvent(index={'t': 0, 'c': 0, 'z': 3}, channel='FITC', min_start_time=0.0, z_pos=2.5, keep_shutter_open=True),
        MDAEvent(index={'t': 0, 'c': 0, 'z': 4}, channel='FITC', min_start_time=0.0, z_pos=5.0),
        MDAEvent(index={'t': 0, 'c': 1, 'z': 2}, channel='DIC', min_start_time=0.0, z_pos=0.0),
        MDAEvent(index={'t': 1, 'c': 0, 'z': 0}, channel='FITC', min_start_time=2.0, z_pos=-5.0, keep_shutter_open=True),
        MDAEvent(index={'t': 1, 'c': 0, 'z': 1}, channel='FITC', min_start_time=2.0, z_pos=-2.5, keep_shutter_open=True),
        MDAEvent(index={'t': 1, 'c': 0, 'z': 2}, channel='FITC', min_start_time=2.0, z_pos=0.0, keep_shutter_open=True),
        MDAEvent(index={'t': 1, 'c': 0, 'z': 3}, channel='FITC', min_start_time=2.0, z_pos=2.5, keep_shutter_open=True),
        MDAEvent(index={'t': 1, 'c': 0, 'z': 4}, channel='FITC', min_start_time=2.0, z_pos=5.0),
        MDAEvent(index={'t': 2, 'c': 0, 'z': 0}, channel='FITC', min_start_time=4.0, z_pos=-5.0, keep_shutter_open=True),
        MDAEvent(index={'t': 2, 'c': 0, 'z': 1}, channel='FITC', min_start_time=4.0, z_pos=-2.5, keep_shutter_open=True),
        MDAEvent(index={'t': 2, 'c': 0, 'z': 2}, channel='FITC', min_start_time=4.0, z_pos=0.0, keep_shutter_open=True),
        MDAEvent(index={'t': 2, 'c': 0, 'z': 3}, channel='FITC', min_start_time=4.0, z_pos=2.5, keep_shutter_open=True),
        MDAEvent(index={'t': 2, 'c': 0, 'z': 4}, channel='FITC', min_start_time=4.0, z_pos=5.0),
        MDAEvent(index={'t': 3, 'c': 0, 'z': 0}, channel='FITC', min_start_time=6.0, z_pos=-5.0, keep_shutter_open=True),
        MDAEvent(index={'t': 3, 'c': 0, 'z': 1}, channel='FITC', min_start_time=6.0, z_pos=-2.5, keep_shutter_open=True),
        MDAEvent(index={'t': 3, 'c': 0, 'z': 2}, channel='FITC', min_start_time=6.0, z_pos=0.0, keep_shutter_open=True),
        MDAEvent(index={'t': 3, 'c': 0, 'z': 3}, channel='FITC', min_start_time=6.0, z_pos=2.5, keep_shutter_open=True),
        MDAEvent(index={'t': 3, 'c': 0, 'z': 4}, channel='FITC', min_start_time=6.0, z_pos=5.0),
        MDAEvent(index={'t': 3, 'c': 1, 'z': 2}, channel='DIC', min_start_time=6.0, z_pos=0.0),
        MDAEvent(index={'t': 4, 'c': 0, 'z': 0}, channel='FITC', min_start_time=8.0, z_pos=-5.0, keep_shutter_open=True),
        MDAEvent(index={'t': 4, 'c': 0, 'z': 1}, channel='FITC', min_start_time=8.0, z_pos=-2.5, keep_shutter_open=True),
        MDAEvent(index={'t': 4, 'c': 0, 'z': 2}, channel='FITC', min_start_time=8.0, z_pos=0.0, keep_shutter_open=True),
        MDAEvent(index={'t': 4, 'c': 0, 'z': 3}, channel='FITC', min_start_time=8.0, z_pos=2.5, keep_shutter_open=True),
        MDAEvent(index={'t': 4, 'c': 0, 'z': 4}, channel='FITC', min_start_time=8.0, z_pos=5.0),
        MDAEvent(index={'t': 5, 'c': 0, 'z': 0}, channel='FITC', min_start_time=10.0, z_pos=-5.0, keep_shutter_open=True),
        MDAEvent(index={'t': 5, 'c': 0, 'z': 1}, channel='FITC', min_start_time=10.0, z_pos=-2.5, keep_shutter_open=True),
        MDAEvent(index={'t': 5, 'c': 0, 'z': 2}, channel='FITC', min_start_time=10.0, z_pos=0.0, keep_shutter_open=True),
        MDAEvent(index={'t': 5, 'c': 0, 'z': 3}, channel='FITC', min_start_time=10.0, z_pos=2.5, keep_shutter_open=True),
        MDAEvent(index={'t': 5, 'c': 0, 'z': 4}, channel='FITC', min_start_time=10.0, z_pos=5.0)
    ]
    ```

### A note on syntax

If you prefer, you can use `useq` objects rather than `dicts`
for all of these fields. This has the advantage of providing
type-checking and auto-completion in your IDE.

!!! example

    The following two sequences are equivalent:

    ```python
    import useq

    mda_sequence1 = useq.MDASequence(
        time_plan={"interval": 2, "loops": 10},
        z_plan={"range": 4, "step": 0.5},
        channels=[
            {"config": "DAPI", "exposure": 50},
            {"config": "FITC", "exposure": 80},
        ]
    )

    mda_sequence2 = useq.MDASequence(
        time_plan=useq.TIntervalLoops(interval=2, loops=10),
        z_plan=useq.ZRangeAround(range=4, step=0.5),
        channels=[
            useq.Channel(config="DAPI", exposure=50),
            useq.Channel(config="FITC", exposure=80),
        ]
    )

    assert mda_sequence1 == mda_sequence2
    ```

## Running an MDA sequence

You may have noticed above that we could call `list()` on an instance of
`MDASequence` to get a list of `MDAEvent` objects. This means that `MDASequence`
**_is_** an [iterable](https://docs.python.org/3/glossary.html#term-iterable) of
`MDAEvent`... which is exactly what we need to pass to the
[`run_mda()`][pymmcore_plus.CMMCorePlus.run_mda] method.

So, you can directly pass an instance of `MDASequence` to `run_mda`:

```python
from pymmcore_plus import CMMCorePlus
import useq

mmc = CMMCorePlus.instance()
mmc.loadSystemConfiguration()

# create a sequence
mda_sequence = useq.MDASequence(
    time_plan={"interval": 2, "loops": 10},
    z_plan={"range": 4, "step": 0.5},
    channels=[
        {"config": "DAPI", "exposure": 50},
        {"config": "FITC", "exposure": 20},
    ]
)

# Run it!
mmc.run_mda(mda_sequence)
```

## Handling acquired data

You will almost certainly want to _do_ something with the
data that is collected during an MDA :joy:. `pymmcore-plus`
is relatively agnostic about how acquired data is handled.
There are currently no built-in methods for saving data to
disk in any particular format.

This is partially because there are so many good existing
ways to store array data to disk in Python, including:

- [zarr](https://zarr.readthedocs.io/en/stable/)
- [tifffile](https://github.com/cgohlke/tifffile)
- [numpy](https://numpy.org/doc/stable/reference/generated/numpy.save.html)
- [xarray](http://xarray.pydata.org/en/stable/io.html)
- [aicsimageio](https://github.com/AllenCellModeling/aicsimageio)
- [netCDF4](https://github.com/Unidata/netcdf4-python)

You will, however, want to know how to connect callbacks to the
[`frameReady`][pymmcore_plus.mda.PMDASignaler.frameReady] event, so that you can
handle incoming data as it is acquired:

```python
from pymmcore_plus import CMMCorePlus
import numpy as np
import useq

mmc = CMMCorePlus.instance()
mmc.loadSystemConfiguration()

@mmc.mda.events.frameReady.connect
def on_frame(image: np.ndarray, event: useq.MDAEvent):
    # do what you want with the data
    print(
        f"received frame: {image.shape}, {image.dtype} "
        f"@ index {event.index}, z={event.z_pos}"
    )

mda_sequence = useq.MDASequence(
    time_plan={"interval": 0.5, "loops": 10},
    z_plan={"range": 4, "step": 0.5},
)

mmc.run_mda(mda_sequence)
```

See [docs for additional
events](http://127.0.0.1:8000/pymmcore-plus/api/events/#pymmcore_plus.mda.events.PMDASignaler)
you may also wish to connect to.

## Cancelling or Pausing

You can pause or cancel the mda with the
[`CMMCorePlus.mda.toggle_pause`][pymmcore_plus.mda._runner.MDARunner.toggle_pause]
or [`CMMCorePlus.mda.cancel`][pymmcore_plus.mda._runner.MDARunner.cancel]
methods.

```python
mmc.mda.toggle_pause()  # pauses the mda
mmc.mda.toggle_pause()  # resumes the mda

mmc.mda.cancel()  # cancels the mda
```

## Serializing MDA sequences

`MDASequence` objects can be serialized and deserialized to and
from JSON or YAML, making it easy to save and load them from
file:

```python
import useq
from pathlib import Path

mda_sequence = useq.MDASequence(
    time_plan={"interval": 2, "loops": 10},
    z_plan={"range": 4, "step": 0.5},
    channels=[
        {"config": "DAPI", "exposure": 50, "do_stack": False},
        {"config": "FITC", "exposure": 20},
    ],
    axis_order="tcz"
)

Path("mda_sequence.yaml").write_text(mda_sequence.yaml())
```

... results in:

```yaml title="mda_sequence.yaml"
axis_order: tcz
channels:
  - config: DAPI
    do_stack: false
    exposure: 50.0
  - config: FITC
    exposure: 20.0
time_plan:
  interval: 0:00:02
  loops: 10
z_plan:
  range: 4.0
  step: 0.5
```

... which can be loaded back into a `MDASequence` object:

```python
mda_sequence = useq.MDASequence.from_file("mda_sequence.yaml")
```

... or even run directly with the `mmcore` command line:

```bash
# use --config to specify a config file for your microscope
$ mmcore run mda_sequence.yaml
```

## Hardware-triggered sequences

Having the computer "in-the-loop" for every event in an MDA sequence, can add
unwanted overhead that limits performance in rapid acquisition sequences.
Because of this, some devices support _hardware triggering_. This means that the
computer can tell the device to queue up and start a sequence of events, and the
device will take care of executing the sequence without further input from the
computer.

Just like [micro-manager's acquisition
engine](https://micro-manager.org/Hardware-based_Synchronization_in_Micro-Manager),
the default acquisition engine in `pymmcore-plus` can opportunistically use
hardware triggering whenever possible. For now, this behavior is off by default
(in order to avoid unexpected behavior), but you can enable it by setting
`CMMCorePlus.mda.engine.use_hardware_sequencing = True`:

```python
from pymmcore_plus import CMMCorePlus

mmc = CMMCorePlus.instance()
mmc.loadSystemConfiguration()

# enable hardware triggering
mmc.mda.engine.use_hardware_sequencing = True
```

!!! question "How does pymmcore-plus know if my device supports hardware triggering?"

    The low-level `CMMCore` object itself has a number of methods that query
    whether certain devices are capable of hardware triggering, such as

    - [`pymmcore.CMMCore.isStageSequenceable`][]
    - [`pymmcore.CMMCore.isPropertySequenceable`][]
    - [`pymmcore.CMMCore.isXYStageSequenceable`][]
    - [`pymmcore.CMMCore.isExposureSequenceable`][]

    If two `MDAEvents` in a sequence have different exposure, stage, or other
    device property values, then `pymmcore-plus` uses these methods to determine whether the
    events can be sequenced (see [`pymmcore_plus.CMMCorePlus.canSequenceEvents`][]).
    If they can, then the events are grouped together
    and executed as a single hardware-triggered sequence.

    ```python
    from pymmcore_plus import CMMCorePlus
    import useq

    mmc = CMMCorePlus.instance()

    mmc.loadSystemConfiguration()
    print(mmc.canSequenceEvents(useq.MDAEvent(), useq.MDAEvent()))  # True
    print(mmc.canSequenceEvents(
        useq.MDAEvent(exposure=50, x_pos=54),
        useq.MDAEvent(exposure=10, x_pos=40)
    ))  # False, unless you have stage and exposure hardware triggering
    ```

## Next steps

Now that you have a basic understanding of how to create and run
multi-dimensional acquisition sequences in pymmcore-plus, you may want to
take a look at some more advanced features:

- using generators and Queues to create non-deterministic sequences
- customizing the acquisition engine
