import pytest

from pymmcore_plus.core.events import CMMCoreSignaler, PCoreSignaler, QCoreSignaler


@pytest.mark.parametrize("cls", [CMMCoreSignaler, QCoreSignaler])
def test_events_protocols(cls):
    obj = cls()
    name = cls.__name__
    if not isinstance(obj, PCoreSignaler):
        required = set(PCoreSignaler.__annotations__)
        raise AssertionError(
            f"{name!r} does not implement the CoreSignaler Protocol. "
            f"Missing attributes: {required - set(dir(obj))!r}"
        )
    for attr, value in PCoreSignaler.__annotations__.items():
        m = getattr(obj, attr)
        if not isinstance(m, value):
            raise AssertionError(
                f"'{name}.{attr}' expected type {value.__name__!r}, got {type(m)}"
            )
