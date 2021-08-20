import operator

import numpy as np
import pymmcore
from useq import MDAEvent

from pymmcore_plus._serialize import SerCMMError, SerMDAEvent, SerNDArray


def _roundtrip(serializer, obj, compare=operator.eq):
    return compare(serializer.from_dict("", serializer.to_dict(obj)), obj)


def test_ndarray():
    assert _roundtrip(SerNDArray, np.random.rand(4, 4), np.allclose)


def test_cmmerror():
    assert _roundtrip(
        SerCMMError, pymmcore.CMMError("msg", 1), lambda a, b: a.getMsg() == b.getMsg()
    )


def test_mda():
    assert _roundtrip(SerMDAEvent, MDAEvent(exposure=42))
