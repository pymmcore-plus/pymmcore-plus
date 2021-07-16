import numpy as np
import pymmcore
from useq import MDAEvent

from pymmcore_plus._serialize import (
    CMMError_to_dict,
    dict_to_CMMError,
    dict_to_mda_event,
    dict_to_ndarray,
    mda_event_to_dict,
    ndarray_to_dict,
)


def test_ndarray():
    data = np.random.rand(4, 4)
    d = ndarray_to_dict(data)
    arr = dict_to_ndarray("", d)
    np.testing.assert_allclose(data, arr)


def test_cmmerror():
    err = pymmcore.CMMError("msg", 1)
    assert dict_to_CMMError("", CMMError_to_dict(err)).getMsg() == err.getMsg()


def test_mda():
    event = MDAEvent(exposure=42)
    d = mda_event_to_dict(event)
    assert dict_to_mda_event("", d) == event
