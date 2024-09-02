import time
from unittest.mock import Mock, call

import numpy as np
import useq

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import mda_listeners_connected


def test_mda_listeners_connected(core: CMMCorePlus) -> None:
    mock = Mock()

    class SlowHandler:
        def frameReady(self, ary: np.ndarray, event: useq.MDAEvent) -> None:
            mock(event.index.get("t"))
            time.sleep(0.01)

    LOOPS = 3
    seq = useq.MDASequence(time_plan=useq.TIntervalLoops(loops=LOOPS, interval=0))

    handler = SlowHandler()

    # by default, we wait for the relay to finish
    # so the mock should be called LOOPS times
    with mda_listeners_connected(handler, mda_events=core.mda.events):
        core.mda.run(seq)

    assert mock.call_count == LOOPS
    mock.assert_has_calls([call(t) for t in range(LOOPS)])

    # FIXME: this test is too flaky ... it depends too critically on timing
    # # with wait_on_exit=False, the mock should be called less than LOOPS times
    # # because the relay is stopped before SlowHandler finishes
    # mock.reset_mock()
    # with mda_listeners_connected(
    #     handler, mda_events=core.mda.events, wait_on_exit=False
    # ):
    #     core.mda.run(seq)
    # assert mock.call_count < LOOPS

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
