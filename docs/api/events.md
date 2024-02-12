# Events

There are two objects that emit events in `pymmcore-plus`:

1. The `CMMCorePlus` object emits events at `CMMCorePlus.events` when the state
   of the microscope changes.
2. The `MDARunner` object emits events at `CMMCorePlus.mda.events` as an
   acquisition sequence progresses.

The events emitted by these two objects are defined by the following protocols:

::: pymmcore_plus.core.events.PCoreSignaler
    options:
        filters: ["^(?!xY|sL).*"]

::: pymmcore_plus.mda.events.PMDASignaler
