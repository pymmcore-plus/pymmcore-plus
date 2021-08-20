import atexit
import datetime
from multiprocessing.shared_memory import SharedMemory
from typing import Deque, Generic, TypeVar

import numpy as np
import pymmcore
import Pyro5
import useq
from pydantic.datetime_parse import parse_duration
from Pyro5.api import register_class_to_dict, register_dict_to_class

Pyro5.config.SERIALIZER = "msgpack"
T = TypeVar("T")


def remove_shm_from_resource_tracker():
    """Monkey-patch multiprocessing.resource_tracker so SharedMemory won't be tracked

    More details at: https://bugs.python.org/issue38119
    """
    from multiprocessing import resource_tracker

    def fix_register(name, rtype):  # pragma: no cover
        if rtype == "shared_memory":
            return
        return resource_tracker._resource_tracker.register(name, rtype)

    resource_tracker.register = fix_register

    def fix_unregister(name, rtype):  # pragma: no cover
        if rtype == "shared_memory":
            return
        return resource_tracker._resource_tracker.unregister(name, rtype)

    resource_tracker.unregister = fix_unregister

    if "shared_memory" in resource_tracker._CLEANUP_FUNCS:
        del resource_tracker._CLEANUP_FUNCS["shared_memory"]


class Serializer(Generic[T]):
    # define these in subclasses
    type_: T

    def to_dict(obj: T) -> dict:
        ...

    def from_dict(classname: str, dct: dict) -> T:
        ...

    # -----------------
    @classmethod
    def _to_dict(cls, obj: T) -> dict:
        return {"__class__": cls.type_key, **cls.to_dict(obj)}

    @classmethod
    def register(cls):
        register_class_to_dict(cls.type_, cls._to_dict)
        register_dict_to_class(cls.type_key, cls.from_dict)

    @classmethod
    def type_key(cls):
        return f"{cls.type_.__module__}.{cls.type_.__name__}"


class SerMDASequence(Serializer[useq.MDASequence]):
    type_ = useq.MDASequence

    def to_dict(obj: useq.MDASequence):
        return obj.dict()

    def from_dict(classname: str, d: dict):
        return useq.MDASequence.parse_obj(d)


class SerMDAEvent(Serializer[useq.MDAEvent]):
    type_ = useq.MDAEvent

    def to_dict(obj: useq.MDAEvent):
        return obj.dict()

    def from_dict(classname: str, d: dict):
        return useq.MDAEvent.parse_obj(d)


class SerTimeDelta(Serializer[datetime.timedelta]):
    type_ = datetime.timedelta

    def to_dict(obj: datetime.timedelta):
        return {"val": str(obj)}

    def from_dict(classname: str, d: dict):
        return parse_duration(d.get("val"))


class SerCMMError(Serializer[pymmcore.CMMError]):
    type_ = pymmcore.CMMError

    def to_dict(obj: pymmcore.CMMError):
        try:
            msg = obj.getMsg()
        except Exception:  # pragma: no cover
            msg = ""
        return {"msg": msg}

    def from_dict(classname: str, d: dict):
        return pymmcore.CMMError(str(d.get("msg")))


class SerNDArray(Serializer[np.ndarray]):
    type_ = np.ndarray
    SHM_SENT: Deque[SharedMemory] = Deque(maxlen=15)

    def to_dict(obj: np.ndarray):
        shm = SharedMemory(create=True, size=obj.nbytes)
        SerNDArray.SHM_SENT.append(shm)
        b = np.ndarray(obj.shape, dtype=obj.dtype, buffer=shm.buf)
        b[:] = obj[:]
        return {
            "shm": shm.name,
            "shape": obj.shape,
            "dtype": str(obj.dtype),
        }

    def from_dict(classname: str, d: dict):
        """convert dict from `ndarray_to_dict` back to np.ndarray"""
        shm = SharedMemory(name=d["shm"], create=False)
        array = np.ndarray(d["shape"], dtype=d["dtype"], buffer=shm.buf).copy()
        shm.close()
        shm.unlink()
        return array

    @classmethod
    def register(cls):
        super().register()


@atexit.register  # pragma: no cover
def _cleanup():
    for shm in SerNDArray.SHM_SENT:
        shm.close()
        try:
            shm.unlink()
        except FileNotFoundError:
            pass


def register_serializers():
    remove_shm_from_resource_tracker()
    SerTimeDelta.register()
    SerNDArray.register()
    SerCMMError.register()
    SerMDASequence.register()
    SerMDAEvent.register()
