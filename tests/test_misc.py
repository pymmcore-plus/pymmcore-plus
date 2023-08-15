from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, call

import pytest
from pymmcore_plus._util import listener_connected, retry
from useq import MDASequence

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus
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
    with listener_connected(
        emitter,
        listener,
    ):
        emitter.signalName.emit(42)
        assert len(emitter.signalName) == 1

    mock.assert_called_once_with(42)
    assert len(emitter.signalName) == 0


def test_core_listener(core: CMMCorePlus):
    mock = Mock()

    class DataHandler:
        def sequenceStarted(self, seq):
            mock(seq)

        def frameReady(self, img, event):
            mock(event)

        def sequenceFinished(self, seq):
            mock(seq)

    handler = DataHandler()
    seq = MDASequence(time_plan={"interval": 0, "loops": 1})

    with core.mda.events.listeners(handler):
        core.mda.run(seq)

    event1 = next(iter(seq))
    mock.assert_has_calls([call(seq), call(event1), call(seq)])
