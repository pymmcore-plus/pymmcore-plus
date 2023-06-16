"""Module vendored from psygnal. Only for internal use."""
from __future__ import annotations

import weakref
from functools import partial
from types import MethodType
from typing import TYPE_CHECKING, Any, Callable, Union

if TYPE_CHECKING:
    from typing import Tuple

    from typing_extensions import TypeGuard

    MethodRef = Tuple[weakref.ReferenceType[object], str, Callable | None]
    NormedCallback = Union[MethodRef, Callable]
    StoredSlot = Tuple[NormedCallback, int | None]
    ReducerFunc = Callable[[tuple, tuple], tuple]


def normalize_slot(slot: Callable | NormedCallback) -> NormedCallback:
    if isinstance(slot, MethodType):
        return (*_get_method_name(slot), None)
    if _is_partial_method(slot):
        return _partial_weakref(slot)
    if isinstance(slot, tuple) and not isinstance(slot[0], weakref.ref):
        return (weakref.ref(slot[0]), slot[1], slot[2])
    return slot


def _partial_weakref(slot_partial: partial) -> tuple[weakref.ref, str, Callable]:
    """For partial methods, make the weakref point to the wrapped object."""
    ref, name = _get_method_name(slot_partial.func, MethodType)  # type: ignore
    args_ = slot_partial.args
    kwargs_ = slot_partial.keywords

    def wrap(*args: Any, **kwargs: Any) -> Any:
        getattr(ref(), name)(*args_, *args, **kwargs_, **kwargs)

    return (ref, name, wrap)


def _is_partial_method(inst: object) -> TypeGuard[partial]:
    return isinstance(inst, partial) and isinstance(inst.func, MethodType)


def _get_method_name(slot: MethodType) -> tuple[weakref.ref, str]:
    obj = slot.__self__
    # some decorators will alter method.__name__, so that obj.method
    # will not be equal to getattr(obj, obj.method.__name__).
    # We check for that case here and find the proper name in the function's closures
    if getattr(obj, slot.__name__, None) != slot:
        for c in slot.__closure__ or ():
            cname = getattr(c.cell_contents, "__name__", None)
            if cname and getattr(obj, cname, None) == slot:
                return weakref.ref(obj), cname
        # slower, but catches cases like assigned functions
        # that won't have function in closure
        for name in reversed(dir(obj)):  # most dunder methods come first
            if getattr(obj, name) == slot:
                return weakref.ref(obj), name
        # we don't know what to do here.
        raise RuntimeError(  # pragma: no cover
            f"Could not find method on {obj} corresponding to decorated function {slot}"
        )
    return weakref.ref(obj), slot.__name__


def denormalize_slot(slot: NormedCallback) -> Callable | None:
    if not isinstance(slot, tuple):
        return slot

    _ref, name, method = slot
    obj = _ref()
    if obj is None:
        return None
    if method is not None:
        return method
    _cb = getattr(obj, name, None)
    return None if _cb is None else _cb
