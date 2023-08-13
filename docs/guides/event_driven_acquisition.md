# Event-Driven Acquisition

!!! warning "Important"

    This page assumes you have a basic understanding of how the default MDA
    acquisition engine works to execute a sequence of `useq.MDAEvent` objects.
    If you haven't already done so, please read the [Acquisition
    Engine](./mda_engine.md) guide first.

You may not always know the exact sequence of events that you want to execute
ahead of time. For example, you may want to start acquiring images at a certain
frequency, but then take a burst of images at a faster frame rate or in a
specific region of interest when a specific (possibly rare) event occurs. This
is sometimes referred to as **event-driven acquisition**, or "smart-microscopy".

!!! info "In publications"

    For two compelling examples of this type of event-driven microscopy, see:

    1. Mahecic D, Stepp WL, Zhang C, Griffié J, Weigert M, Manley S.
    *Event-driven acquisition for content-enriched microscopy.*
    Nat Methods 19, 1262–1267 (2022).
    [https://doi.org/10.1038/s41592-022-01589-x](https://doi.org/10.1038/s41592-022-01589-x)

    2. Shi Y, Tabet JS, Milkie DE, Daugird TA, Yang CQ, Giovannucci A, Legant WR.
    *Smart Lattice Light Sheet Microscopy for imaging rare and complex cellular events.*
    bioRxiv. 2023 Mar 9
    [https://doi.org/10.1101/2023.03.07.531517.](https://doi.org/10.1101/2023.03.07.531517)

Obviously, in this case, you can't just create a list of `useq.MDAEvent` objects
and pass them to the acquisition engine, since that list needs to change based
on the results of previous events.

Fortunately, the [`MDARunner.run()`][pymmcore_plus.mda.MDARunner.run] method
is designed to handle this case.

## `Iterable[MDAEvent]`

The key thing to observe here is the signature of the
[`MDARunner.run()`][pymmcore_plus.mda.MDARunner.run] method:

```python
from typing import Iterable
import useq

class MDARunner:
    def run(self, events: Iterable[useq.MDAEvent]) -> None: ...
```

:eyes: **The `run` method expects an _iterable_ of `useq.MDAEvent`
objects.** :eyes:

!!! question "Iterable"

    An [`Iterable`][collections.abc.Iterable] is any object that implements an
    `__iter__()` method that returns an [iterator
    object](https://docs.python.org/3/library/stdtypes.html#iterator-types). This
    includes sequences of known length, like `list`, `tuple`, but also many other
    types of objects, such as
    [generators](https://docs.python.org/3/library/stdtypes.html#generator-types),
    [`deque`][collections.deque], and more. Other types such as
    [`Queue`][queue.Queue] can easily be converted to an iterator as well, as we'll
    see below.

## Useful Iterables

Many python objects are iterable. Let's look at a few types of iterables that
can be used to implement event-driven acquisition in pymmcore-plus.

### Generators

[Generator functions](https://docs.python.org/3/glossary.html#index-19) are
functions that contain `yield` statements. When called, they return a [generator
iterator](https://docs.python.org/3/glossary.html#term-generator-iterator) that
can be used to iterate over the values yielded by the generator function. 

!!! question "Say what?"

    That
    may sound a bit confusing, but it's actually quite simple.  It just means that
    you can use the output of a generator function in a for loop:

    ```python
    from typing import Iterator

    # a generator function, which contains "yield" statements
    def my_generator_func() -> Iterator[int]:
        yield 1
        yield 2

    # calling the function returns an iterator
    gen_iterator = my_generator_func()

    # which we can iterate over (e.g. in a for loop)
    for value in gen_iterator:
        print(value)  # prints 1, then 2
    ```

Let's create a generator that yields `useq.MDAEvent`
objects, but simulate a "burst" of events when a certain condition is met:

```python
import random
import time
from typing import Iterator

import useq

def some_condition_is_met() -> bool:
    # Return True 20% of the time ...
    # Just an example of some probabilistic condition
    # This could be anything, the results of analysis, etc.
    return random.random() < 0.2

# generator function that yields events
def my_events() -> Iterator[useq.MDAEvent]:
    i = 0
    while True:
        if some_condition_is_met():
            # yield a burst of events
            for _ in range(5):
                yield useq.MDAEvent(metadata={'bursting': True})
        elif i > 5:
            # stop after 5 events
            # (just an example of some stop condition)
            return
        else:
            # yield a regular single event
            yield useq.MDAEvent()

        # wait a bit before yielding the next event (1)
        time.sleep(0.1)
        i += 1
```

1. Note, we could also take advantage of the `min_start_time`
   field in MDAEvent, but this demonstrates that the generator
   can also control the timing of events.

??? example "example output of `list(my_events())`"

    We can use the `list()` function to iterate over the generator
    and collect the yielded events:

    ```python
    list(my_events())
    ```

    Because of the random condition, the output will be different each time,
    but it might look something like this:

    ```python
    [
        MDAEvent(),
        MDAEvent(metadata={'bursting': True}),  # (1)!
        MDAEvent(metadata={'bursting': True}),
        MDAEvent(metadata={'bursting': True}),
        MDAEvent(metadata={'bursting': True}),
        MDAEvent(metadata={'bursting': True}),
        MDAEvent(),
        MDAEvent(),
        MDAEvent(),
        MDAEvent() # (2)!
    ]
    ```

    1. `some_condition_is_met` returned `True` on the second iteration,
       so the generator yielded a burst of events.
    2. Our "stop condition" of `i > 5` was met, so the generator returned
       and stopped yielding events.

To run this "experiment" using pymmcore-plus, we can pass the output of the
generator to the `MDARunner.run()` method:

```python
from pymmcore_plus import CMMCorePlus

core = CMMCorePlus()
core.loadSystemConfiguration()

core.run_mda(my_events())
```

### Queues

Python's [`Queue`][queue.Queue] class is useful for managing and synchronizing
data between multiple threads or processes. It ensures orderly execution and
prevents race conditions. Generally, a Queue is passed between threads or
processes, and one thread or process
[puts](https://docs.python.org/3/library/queue.html#queue.Queue.put) data (such
as an `MDAEvent` to execute) into the queue, while another thread or process
[gets](https://docs.python.org/3/library/queue.html#queue.Queue.get) data out of
the queue.

A `Queue` instance itself is not an iterable...

!!! failure ":thumbsdown:"

    ```python
    >>> from queue import Queue
    >>> list(Queue())
    Traceback (most recent call last):
    File "<stdin>", line 1, in <module>
    TypeError: 'Queue' object is not iterable
    ```

however, a `Queue` can be easily converted to an iterator using the two-argument
version of the builtin [`iter()`][iter] function:

!!! success ":thumbsup:"

    ```python
    >>> from queue import Queue
    >>> q = Queue()
    >>> q.put(1)
    >>> q.put(2)
    >>> q.put('STOP')
    >>> iterable_queue = iter(q.get, 'STOP') # !! (1)
    >>> list(iterable_queue)
    [1, 2]
    ```

    1. :tophat: Thanks [Kyle Douglass](https://github.com/kmdouglass) for discovering
    this handy, if obscure, second argument to `iter()`!

We can use this `iter(queue.get, sentinel)` pattern to create a queue-backed
iterable that can be passed to the `run_mda()` method. The acquisition engine
will then execute events as they get `put` into the queue, until the stop
sentinel is encountered.

```python
from queue import Queue
from pymmcore_plus import CMMCorePlus
from useq import MDAEvent

core = CMMCorePlus()
core.loadSystemConfiguration()

q = Queue()                    # create the queue
STOP = object()                # any object can serve as the sentinel
q_iterator = iter(q.get, STOP) # create the queue-backed iterable

# start the acquisition in a separate thread
core.run_mda(q_iterator)

# (optional) connect some callback to the imageReady signal
@core.mda.events.frameReady.connect
def on_frame(img, event):
    print(f'Frame {event.index} received: {img.shape}')

# now we can put events into the queue
# according to whatever logic we want:
q.put(MDAEvent(index={'t': 0}, exposure=20))
q.put(MDAEvent(index={'t': 1}, exposure=40))

# ... and eventually stop the acquisition
q.put(STOP)
```

??? example "More complete event-driven acquisition example"

    The following example is modified from
    [this gist](https://gist.github.com/kmdouglass/d15a0410d54d6b12df8614b404d9b751)
    by [Kyle Douglass](https://gist.github.com/kmdouglass).

    It simulates a typical event-driven acquisition, where an Analyzer object
    analyzes the results of each image and provides a dict of results. The
    Controller object then decides whether to continue or stop the acquisition
    (by placing the `STOP_EVENT` sentinel in the queue).

    ```python linenums="1" title="event_driven_acquisition.py"
    --8<-- "examples/event_driven_acquisition.py"
    ```

### MDASequence

It's worth noting that the [`MDASequence`][useq.MDASequence] class is itself an
`Iterable[MDAEvent]`. It implements an `__iter__` method that yields the events
in the sequence, and it can be passed directly to the `run_mda()` method as we
saw in the [Acquisition engine guide](mda_engine.md#running-an-mda-sequence). It
is a _deterministic_ sequence, so it wouldn't be used on its own to implement
conditional event sequences; it can, however, be used in conjunction with other
iterables to implement more complex sequences.

Take this simple sequence as an example:

```python
my_sequence = useq.MDASequence(
    time_plan={'loops': 5, 'interval': 0.1},
    channels=["DAPI", "FITC"]
)
```

In the generator example above, we could yield the events in this sequence
when the condition is met (saving us from constructing the events
manually)

```python
# example usage in the
def my_events() -> Iterator[useq.MDAEvent]:
    while True:
        if some_condition_is_met():
            yield from my_sequence  # yield the events in the sequence
        else:
            ...
```

In the `Queue` example above, we could `put` the events in the sequence into the
queue:

```python
# ... we can put events into the queue
# according to whatever logic we want:
for event in my_sequence:
    q.put(event)
```