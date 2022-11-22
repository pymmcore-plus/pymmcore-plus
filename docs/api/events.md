# Events

Both the [`CMMCorePlus`][pymmcore_plus.CMMCorePlus] object and the
[`CMMCorePlus.mda`][pymmcore_plus.CMMCorePlus.mda] (`MDARunner`) objects have
`events` attributes that can be used to register callbacks for events that occur
as the state of the microscope changes, or as an acquisition sequences progresses.

These events are defined here.

::: pymmcore_plus.core.events.PCoreSignaler
    options:
        filters: ["^(?!xY|sL).*"]

::: pymmcore_plus.mda.events.PMDASignaler
