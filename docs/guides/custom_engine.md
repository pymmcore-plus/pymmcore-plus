# Custom Acquisition Engines

!!! warning "Important"

    This page assumes you have a basic understanding of how the default MDA
    acquisition engine works to execute a sequence of `useq.MDAEvent` objects.
    If you haven't already done so, please read the [Acquisition
    Engine](./mda_engine.md) guide first.

While the default MDA acquisition engine is sufficient for many common use
cases, you may find that you need to customize the acquisition engine to
accomplish your goals. Cases where you may need to customize the acquisition
engine include:

- Driving hardware for which a [micro-manager device
  adapter](https://micro-manager.org/Device_Support) does not exist.
- Conditionally executing arbitrary python code before, during, or after
  each acquisition event.
- Using an alternate [high-performance camera
  driver](https://github.com/nclack/acquire-python)
- Handling user-specific [`MDAEvent.metadata`][useq.MDAEvent] values.
- Intercepting and modifying the event sequence<sup>\*</sup>.

    !!! info "<sup>\*</sup>Note"

        If *all* you want to is to modify the event sequence (e.g. to add
        additional events in a non-deterministic way) but you don't need to
        modify the behavior of the acquisition engine itself, you likely
        don't need to customize the acquisition engine. See the guide on
        [Event-Driven Acquisition](event_driven_acquisition.md) for details.

## The `MDARunner` and `MDAEngine`

Let's start by taking a quick look at how the acquisition logic in
pymmcore-plus is structured. There are two key classes involved:

1. An [**`MDARunner`**][pymmcore_plus.mda.MDARunner] instance is
   responsible for receiving a sequence of `useq.MDAEvent` objects and
   driving an `MDAEngine` to execute them. The `MDARunner` is the object that
   has the actual [`run()`][pymmcore_plus.mda.MDARunner.run] method. It also
   emits all the events, such as
   [`frameReady`][pymmcore_plus.mda.PMDASignaler.frameReady]. Users shouldn't
   need to subclass or modify `MDARunner` directly.
1. An `MDAEngine` instance (anything that implements the
   [**`PMDAEngine`** protocol](#the-mdaengine-protocol)) is responsible for
   actually setting up and executing each event in the sequence. The default
   implementation of the `PMDAEngine` protocol is the
   [**`MDAEngine`**][pymmcore_plus.mda.MDAEngine] class, but you can register
   your own custom engine, using either a subclass of the default engine,
   or any other object that implements the `PMDAEngine` protocol.

```python
from pymmcore_plus import CMMCorePlus

core = CMMCorePlus()

core.mda          # <- The MDARunner instance
core.mda.engine   # <- The MDAEngine instance
```

## The `MDAEngine` Protocol

`pymmcore-plus` defines a protocol (a.k.a. "interface" in the Java world) that
all acquisition engines must implement. Formal API docs for the protocol can be
found [here][pymmcore_plus.mda.PMDAEngine], but let's discuss the three key
methods here.

1. [`setup_sequence()`][pymmcore_plus.mda.PMDAEngine.setup_sequence] -
   Setup state of system before an MDA is run.
2. [`setup_event()`][pymmcore_plus.mda.PMDAEngine.setup_event] -
   Prepare state of system for an event.
3. [`exec_event()`][pymmcore_plus.mda.PMDAEngine.exec_event]
   Execute the event.

!!! important "The `PMDAEngine` Protocol"

    ```python
    class MyEngine:
        def setup_sequence(self, sequence: MDASequence) -> SummaryMetaV1 | None:
            """Setup state of system (hardware, etc.) before an MDA is run.

            This method is called once at the beginning of a sequence.
            (The sequence object needn't be used here if not necessary)
            """

        def setup_event(self, event: MDAEvent) -> None:
            """Prepare state of system (hardware, etc.) for `event`.

            This method is called before each event in the sequence. It is
            responsible for preparing the state of the system for the event.
            The engine should be in a state where it can call `exec_event`
            without any additional preparation.
            """

        def exec_event(self, event: MDAEvent) -> Iterable[tuple[NDArray, MDAEvent, FrameMetaV1]]:
            """Execute `event`.

            This method is called after `setup_event` and is responsible for
            executing the event. The default assumption is to acquire an image,
            but more elaborate events will be possible.
            """
    ```

The following methods are optional, but will be used if they are defined:

1. [`event_iterator()`][pymmcore_plus.mda.PMDAEngine.event_iterator] -
   Optional wrapper on the event iterator. To customize the event sequence.
2. `teardown_event()` -
   Called after `exec_event()`. To clean up after an event.
3. `teardown_sequence()`
   Called after the sequence is complete. To clean up after an MDA.

## The built-in `MDAEngine`

The default implementation of the `PMDAEngine` protocol is the
[**`MDAEngine`**][pymmcore_plus.mda.MDAEngine] class. It can handle microscope
setup and image acquisition for a standard `MDAEvent`, and opportunistically queues
[hardware-triggered sequences](mda_engine.md#hardware-triggered-sequences). It also serves as a good base
class for custom engines if you want to extend the default behavior. (You may
also find the [source
code](https://github.com/pymmcore-plus/pymmcore-plus/blob/main/src/pymmcore_plus/mda/_engine.py)
for the `MDAEngine` class helpful as a reference when writing a custom engine.)

## Customizing the `MDAEngine`

If you want to customize _how_ the instrument sets up or executes each event,
the easiest approach is to subclass the default `MDAEngine` class and override
or extend the methods you need to customize, then register your custom engine
with the runner's [`set_engine()`][pymmcore_plus.mda.MDARunner.set_engine]
method.

```python
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine
import useq

class MyEngine(MDAEngine): # (1)!
    def setup_event(self, event: useq.MDAEvent) -> None:
        """Prepare state of system (hardware, etc.) for `event`."""
        # do some custom pre-setup
        super().setup_event(event)  # (2)!
        # do some custom post-setup

    def exec_event(self, event: useq.MDAEvent) -> object:
        """Prepare state of system (hardware, etc.) for `event`."""
        # do some custom pre-execution
        result = super().exec_event(event)  # (3)!
        # do some custom post-execution
        return result # (4)!

core = CMMCorePlus.instance()
core.loadSystemConfiguration()

# Register the custom engine with the runner
core.mda.set_engine(MyEngine(core))  # (5)!

# Run an MDA
core.run_mda([])
```

1. Create a custom engine by subclassing the default engine
2. Note that it's not required to call the `super()` method here
   if you don't want to
3. Note that it's not required to call the `super()` method here
   if you don't want to
4. If the object returned by `exec_event()` has an `image` attribute,
   it will be used to emit the `frameReady` event. A simple implementation
   might use a named tuple:
   ```python
   class EventPayload(typing.NamedTuple):
       image: np.ndarray | None = None
   ```
5. Note that `MDAEngine.__init__` accepts a `CMMCorePlus` instance
   as its first argument, so you'll need to pass that in when
   instantiating your custom engine.

## Utilizing `MDAEvent` metadata

More often than not, if you are customizing the acquisition engine, it will
be because you'd like to do something _other_ than drive the micro-manager
core to set up and acquire an image. Perhaps you need to control a micro-fluidic
device, or control a DAQ card, or communicate with a remote server, etc.

In all of these cases, you will likely need additional parameters (beyond
the fields defined in the `MDAEvent` class) to pass to your control code.
For this, the `MDAEvent` class has a `metadata` attribute that is explicitly
provided for user-defined data.

```python
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine
import useq

class MyEngine(MDAEngine):
    def setup_event(self, event: useq.MDAEvent) -> None:
        if 'my_key' in event.metadata:  # (1)!
            self._my_custom_setup(event.metadata)
        else:
            super().setup_event(event)

    def _my_custom_setup(self, metadata: dict) -> None:
        print(f"Setting up my custom device with {metadata}")

    def exec_event(self, event: useq.MDAEvent) -> object:
        if 'my_key' in event.metadata:
            return self._my_custom_exec(event.metadata)  # (2)!
        else:
            return super().exec_event(event)

    def _my_custom_exec(self, metadata: dict) -> object:
        print(f"Executing my custom stuff with {metadata}")

core = CMMCorePlus.instance()
core.loadSystemConfiguration()

core.mda.set_engine(MyEngine(core))

experiment = [
    useq.MDAEvent(),
    useq.MDAEvent(metadata={'my_key': {'param1': 'val1'}}),  # (3)!
    useq.MDAEvent(),
    useq.MDAEvent(metadata={'my_key': {'param1': 'val2'}}),
]

core.run_mda(experiment)
```

1. You can use any characteristics of the `MDAEvent`, such as the `index`, or
   the presence of a special key in the `metadata` attribute, to determine
   whether you want to do something special for that event.
2. You don't _have_ to return here. If you also want to do the default image
   acquisition, you can call `super().exec_event(event)` as well.
3. Add metadata to the event. You can do this either by constructing your own
   sequence of `MDAEvent` objects, or by using
   [`MDASequence`](mda_engine.md#building-sequences-with-mdasequence) to build
   the sequence for you, then editing the `metadata` attributes as needed.

!!! example

    For a real-world example of an `MDAEngine` subclass that uses
    `MDAEvent.metadata` to drive hardware for Raman spectroscopy,
    see Ian Hunt-Isaak's
    [raman-mda-engine](https://github.com/ianhi/raman-mda-engine).
    (engine subclass
    [here](https://github.com/ianhi/raman-mda-engine/blob/main/raman_mda_engine/_engine.py))
