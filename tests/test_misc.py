from __future__ import annotations

from unittest.mock import Mock

import pytest

from pymmcore_plus._util import listeners_connected, retry


def test_retry() -> None:
    i: int = 0

    def works_on_third_try(x: str) -> str:
        nonlocal i
        i += 1
        if i < 3:
            raise ValueError("nope")
        return x

    with pytest.raises(ValueError, match="nope"):
        retry(tries=3, exceptions=RuntimeError, delay=0.5)(works_on_third_try)(1)

    i = 0
    mock = Mock()
    good_retry = retry(tries=3, exceptions=ValueError, logger=mock)(works_on_third_try)

    assert good_retry("hi") == "hi"
    assert mock.call_count == 2
    mock.assert_called_with("ValueError nope caught, trying 1 more times")


def test_listener_connected() -> None:
    from psygnal import Signal

    mock = Mock()
    mock2 = Mock()

    class Emitter:
        signal1 = Signal(int)

    class Listener:
        def signal1(self, value: int) -> None:
            mock(value)

        def method_2(self, value: int) -> None:
            mock2(value)

    emitter = Emitter()
    listener = Listener()

    assert len(emitter.signal1) == 0
    with listeners_connected(emitter, listener):
        emitter.signal1.emit(42)
        assert len(emitter.signal1) == 1

    mock.assert_called_once_with(42)
    mock2.assert_not_called()
    assert len(emitter.signal1) == 0

    # now connect to a different method
    mock.reset_mock()
    with listeners_connected(emitter, listener, name_map={"signal1": "method_2"}):
        emitter.signal1.emit(42)

    mock2.assert_called_once_with(42)
    mock.assert_not_called()
