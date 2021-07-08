import atexit
import datetime
from multiprocessing.shared_memory import SharedMemory
from typing import Deque

import numpy as np
import pymmcore
import Pyro5
import useq
from pydantic.datetime_parse import parse_duration
from Pyro5.api import register_class_to_dict, register_dict_to_class

Pyro5.config.SERIALIZER = "msgpack"

MAX_SHM = 10
SHM_SENT: Deque[SharedMemory] = Deque(maxlen=MAX_SHM)
SHM_RECV: Deque[SharedMemory] = Deque(maxlen=MAX_SHM)


@atexit.register
def _cleanup():
    for shm in SHM_RECV:
        shm.close()
    for shm in SHM_SENT:
        shm.close()
        shm.unlink()


def ndarray_to_dict(obj: np.ndarray):
    """convert numpy array to dict."""
    shm = SharedMemory(create=True, size=obj.nbytes)
    SHM_SENT.append(shm)
    b = np.ndarray(obj.shape, dtype=obj.dtype, buffer=shm.buf)
    b[:] = obj[:]
    return {
        "__class__": "numpy.ndarray",
        "shm": shm.name,
        "shape": obj.shape,
        "dtype": str(obj.dtype),
    }


def dict_to_ndarray(classname, d):
    """convert dict from `ndarray_to_dict` back to np.ndarray"""
    shm = SharedMemory(name=d["shm"], create=False)
    SHM_RECV.append(shm)
    return np.ndarray(d["shape"], dtype=d["dtype"], buffer=shm.buf)


def CMMError_to_dict(err):
    try:
        msg = err.args[0].getFullMsg()
    except Exception:
        msg = ""
    return {
        "__class__": "pymmcore.CMMError",
        "msg": msg,
    }


def dict_to_CMMError(classname, d):
    return pymmcore.CMMError(str(d.get("msg")))


def timedelta_to_dict(obj):
    return {
        "__class__": "datetime.timedelta",
        "val": str(obj),
    }


def dict_to_timedelta(classname, d):
    return parse_duration(d.get("val"))


def mdaseq_to_dict(mda_sequence: useq.MDASequence):
    return {
        "__class__": "useq.MDASequence",
        "val": mda_sequence.dict(),
    }


def dict_to_mdaseq(classname, d):
    return useq.MDASequence.parse_obj(d.get("val"))


def mda_event_to_dict(mda_event: useq.MDAEvent):
    return {
        "__class__": "useq.MDAEvent",
        "val": mda_event.dict(),
    }


def dict_to_mda_event(classname, d):
    return useq.MDAEvent.parse_obj(d.get("val"))


def remove_shm_from_resource_tracker():
    """Monkey-patch multiprocessing.resource_tracker so SharedMemory won't be tracked

    More details at: https://bugs.python.org/issue38119
    """
    from multiprocessing import resource_tracker

    def fix_register(name, rtype):
        if rtype == "shared_memory":
            return
        return resource_tracker._resource_tracker.register(name, rtype)

    resource_tracker.register = fix_register

    def fix_unregister(name, rtype):
        if rtype == "shared_memory":
            return
        return resource_tracker._resource_tracker.unregister(name, rtype)

    resource_tracker.unregister = fix_unregister

    if "shared_memory" in resource_tracker._CLEANUP_FUNCS:
        del resource_tracker._CLEANUP_FUNCS["shared_memory"]


def register_serializers():
    remove_shm_from_resource_tracker()

    register_class_to_dict(np.ndarray, ndarray_to_dict)
    register_dict_to_class("numpy.ndarray", dict_to_ndarray)

    register_class_to_dict(pymmcore.CMMError, CMMError_to_dict)
    register_dict_to_class("pymmcore.CMMError", dict_to_CMMError)

    register_class_to_dict(datetime.timedelta, timedelta_to_dict)
    register_dict_to_class("datetime.timedelta", dict_to_timedelta)

    register_class_to_dict(useq.MDASequence, mdaseq_to_dict)
    register_dict_to_class("useq.MDASequence", dict_to_mdaseq)

    register_class_to_dict(useq.MDAEvent, mda_event_to_dict)
    register_dict_to_class("useq.MDAEvent", dict_to_mda_event)
