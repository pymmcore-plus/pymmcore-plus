import pymmcore_plus
import pytest
from _pytest.logging import LogCaptureFixture
from pymmcore_plus._logger import logger
from pymmcore_plus.core.events import CMMCoreSignaler, QCoreSignaler
from pymmcore_plus.mda.events import MDASignaler, QMDASignaler


@pytest.fixture(params=["QSignal", "psygnal"], scope="function")
def core(request):
    core = pymmcore_plus.CMMCorePlus()
    if request.param == "psygnal":
        core._events = CMMCoreSignaler()
        core.mda._events = MDASignaler()
    else:
        core._events = QCoreSignaler()
        core.mda._events = QMDASignaler()
    core._callback_relay = pymmcore_plus.core._mmcore_plus.MMCallbackRelay(core.events)
    core.registerCallback(core._callback_relay)
    if not core.getDeviceAdapterSearchPaths():
        pytest.fail("To run tests, please install MM with `mmcore install`")
    core.loadSystemConfiguration()
    return core


@pytest.fixture
def caplog(caplog: LogCaptureFixture):
    handler_id = logger.add(caplog.handler, format="{message}")
    try:
        yield caplog
    finally:
        logger.remove(handler_id)
