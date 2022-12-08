# CMMCorePlus

The main object in `pymmcore_plus` is the `pymmcore_plus.CMMCorePlus` class.
`CMMCorePlus` is a subclass of
[`pymmcore.CMMCore`](https://github.com/micro-manager/pymmcore) with additional
functionality, and some overrides for the sake of convenience or fixed behavior.

## CMMCorePlus API summary

This table presents all methods available in the `CMMCorePlus` class, and
indicates which methods are unique to `CMMCorePlus` (:sparkles:) and which
methods are overriden from `CMMCore` (:material-plus-thick:).  Below the
table, the signatures of all methods are presented, broken into a
`CMMCorePlus` section and a `CMMCore` section (depending on whether the
method is implemented in `CMMCorePlus` or not).

<small>
:material-plus-thick:  *This method is overriden by `CMMCorePlus`.*
:sparkles:  *This method only exists in `CMMCorePlus`.*
</small>

<!-- These are built dynamically in _hooks.py -->

{{ CMMCorePlus_API_Table }}

{{ CMMCorePlus_Members }}

----------------

!!! info

    The `pymmcore.CMMCore` methods below are available as inherited methods,
    but are not reimplemented in the `CMMCorePlus` subclass.  They are
    documented here for completeness.

{{ CMMCore_Members }}

----------------

### TypedDicts

::: pymmcore_plus.core._mmcore_plus.StateDict

::: pymmcore_plus.core._mmcore_plus.DeviceSchema

::: pymmcore_plus.core._mmcore_plus.PropertySchema
