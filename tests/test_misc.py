from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from pymmcore_plus._util import listeners_connected, retry

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


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


def test_listener_connected(qtbot: QtBot) -> None:
    from psygnal import Signal

    mock = Mock()

    class Emitter:
        signalName = Signal(int)

    class Listener:
        def signalName(self, value: int) -> None:
            mock(value)

    emitter = Emitter()
    listener = Listener()

    assert len(emitter.signalName) == 0
    with listeners_connected(emitter, listener):
        emitter.signalName.emit(42)
        assert len(emitter.signalName) == 1

    mock.assert_called_once_with(42)
    assert len(emitter.signalName) == 0
