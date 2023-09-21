from typing import TYPE_CHECKING
from unittest.mock import Mock

import useq
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import mda_listeners_connected

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def test_mda_listeners_connected(core: CMMCorePlus, qtbot: "QtBot") -> None:
    mock = Mock()

    class SlowHandler:
        def frameReady(self, ary: np.ndarray, event: useq.MDAEvent):
            mock(event.index.get("t"))
            time.sleep(0.05)

    LOOPS = 4
    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(loops=LOOPS, interval=0.01))

    handler = SlowHandler()

    # by default, we wait for the relay to finish
    # so the mock should be called LOOPS times
    with mda_listeners_connected(handler, mda_events=core.mda.events):
        core.mda.run(seq)

    assert mock.call_count == LOOPS
    # mock.assert_has_calls([call(t) for t in range(LOOPS)])

    # with wait_on_exit=False, the mock should be called less than LOOPS times
    # because the relay is stopped before SlowHandler finishes
    mock.reset_mock()
    with mda_listeners_connected(
        handler, mda_events=core.mda.events, wait_on_exit=False
    ):
        core.mda.run(seq)
    assert mock.call_count < LOOPS

    # make sure it got disconnected
    mock.reset_mock()
    core.mda.events.frameReady.emit(np.empty((10, 10)), useq.MDAEvent(), {})
    mock.assert_not_called()

    # with asynchronous=False, it reduces to a synchronous listeners_connected context
    mock.reset_mock()
    with mda_listeners_connected(
        handler, mda_events=core.mda.events, asynchronous=False
    ):
        core.mda.run(seq)
    assert mock.call_count == LOOPS
