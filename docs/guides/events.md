# Events and Callbacks

!!! warning "Terminology confusion!"

    A quick warning on terminology: the name "event" may refer to two different
    things in pymmcore-plus, which are not to be confused.

    This page discusses the "events" that are emitted by the `CMMCorePlus` and
    `MDARunner` objects.  These are occurrences that your program can react to
    by registering callback functions. These are also known as "**signals**" in the
    context of the Qt framework or psygnal.

    The term "event" may also used to refer to the **`useq.MDAEvent`** objects that
    are consumed by the [Acquisition Engine](../guides/mda_engine.md).
    These are *not* the same as the "events" discussed on this page.

Both the [`CMMCorePlus`][pymmcore_plus.CMMCorePlus] object and the
[`CMMCorePlus.mda`][pymmcore_plus.CMMCorePlus.mda] (`MDARunner`) objects have
`events` attributes that can be used to register callbacks for events that occur
as the state of the microscope changes, or as an acquisition sequences progresses.

## Event backends

`pymmcore-plus` supports both **Qt**-based and
[**psygnal**](https://github.com/pyapp-kit/psygnal)-based event signaling.

**The default behavior is to use Qt-backed signals when a global `QApplication`
instance has been created in the main process, and `psygnal` otherwise.**

If you would like to force a specific event backend, you can do so by
setting the `PYMM_SIGNALS_BACKEND` environment variable to `qt`,
`psygnal`, or `auto` (for the default behavior).

=== "bash/zsh"

    ```bash
    export PYMM_SIGNALS_BACKEND=psygnal
    ```

=== "cmd"
    ```cmd
    set PYMM_SIGNALS_BACKEND=psygnal
    ```

=== "python"
    ```python
    # before instantiating CMMCorePlus
    import os
    os.environ["PYMM_SIGNALS_BACKEND"] = "psygnal"
    ```

=== "powershell"
    ```powershell
    $env:PYMM_SIGNALS_BACKEND = "psygnal"
    ```

## Connecting callbacks to events

To connect a callback to an event, use the `connect` method of specific
event emitter that you would like to listen to.  (All event backends
support the same connection/disconnection API.)

!!!example "Example: Connecting callbacks"
    Given a `CMMCorePlus` object `core`:

    ```python
    from pymmcore_plus import CMMCorePlus

    core = CMMCorePlus()
    ```

    Register a callback to listen to property changes on the `CMMCorePlus`:

    ```python

    @core.events.propertyChanged.connect
    def on_property_changed(dev: str, prop: str, value: str):
        print(f"Property {prop!r} on device {dev!r} changed to {value}")
    ```

    Register a callback to process data during an acquisition sequence:

    ```python
    @core.mda.events.frameReady.connect
    def on_image_captured(data: np.ndarray, event: useq.MDAEvent, metadata: dict):
        print(f"Event index {event.index} captured with shape {data.shape}")
    ```

The signature of the callback function should match the signature of the event
emitter's signal.  See [API documentation][pymmcore_plus.core.events] for the specific
event signatures.

You may **disconnect** a callback from an event by calling the `disconnect` method
of the event emitter with the callback function as the argument.

!!!example "Example: Disconnecting callbacks"
    ```python
    core.events.propertyChanged.disconnect(on_property_changed)
    ```
