# CMMCorePlus

The main object in `pymmcore_plus` is the `pymmcore_plus.CMMCorePlus` class.
`CMMCorePlus` is a subclass of
[`pymmcore.CMMCore`](https://github.com/micro-manager/pymmcore) with additional
functionality, and some overrides for the sake of convenience or fixed behavior.

## CMMCorePlus API summary

This table presents all methods available in the `CMMCorePlus` class, and
indicates which methods are unique to `CMMCorePlus` (:sparkles:) and which
methods are overriden from `CMMCore` (:heavy_plus_sign:).

<small>
:heavy_plus_sign:  *This method is overriden by `CMMCorePlus`.*
:sparkles:  *This method only exists in `CMMCorePlus`.*
</small>

{% include '_cmmcore_table.md' %}

{% include '_cmmcoreplus_members.md' %}

{% include '_cmmcore_members.md' %}
