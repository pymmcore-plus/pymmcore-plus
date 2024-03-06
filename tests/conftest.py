from __future__ import annotations

import os
from unittest.mock import patch

os.environ["PYTEST_RUNNING"] = "1"

import pymmcore_plus  # noqa: E402
import pytest  # noqa: E402
from pymmcore_plus._logger import logger  # noqa: E402
from pymmcore_plus.core.events import CMMCoreSignaler  # noqa: E402
from pymmcore_plus.mda.events import MDASignaler  # noqa: E402

try:
    from pymmcore_plus.core.events import QCoreSignaler
    from pymmcore_plus.mda.events import QMDASignaler

    PARAMS = ["QSignal", "psygnal"]
except ImportError:
    PARAMS = ["psygnal"]


@pytest.fixture(params=PARAMS, scope="function")
def core(request):
    core = pymmcore_plus.CMMCorePlus()
    if request.param == "psygnal":
        core._events = CMMCoreSignaler()
        core.mda._signals = MDASignaler()
    else:
        core._events = QCoreSignaler()
        core.mda._signals = QMDASignaler()
    core._callback_relay = pymmcore_plus.core._mmcore_plus.MMCallbackRelay(core.events)
    core.registerCallback(core._callback_relay)
    if not core.getDeviceAdapterSearchPaths():
        pytest.fail("To run tests, please install MM with `mmcore install`")
    core.loadSystemConfiguration()
    return core


@pytest.fixture
def mock_fullfocus(core: pymmcore_plus.CMMCorePlus):
    def _fullfocus():
        core.setZPosition(core.getZPosition() + 50)

    with patch.object(core, "fullFocus", _fullfocus):
        yield


@pytest.fixture
def mock_fullfocus_failure(core: pymmcore_plus.CMMCorePlus):
    def _fullfocus():
        raise RuntimeError()

    with patch.object(core, "fullFocus", _fullfocus):
        yield


@pytest.fixture
def caplog(caplog: pytest.LogCaptureFixture):
    logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def pytest_collection_modifyitems(session, config, items: list[pytest.Function]):
    # putting test_cli_logs first, because I can't figure out how to mock the log
    # file after the core fixture has been created :/
    items.sort(key=lambda item: item.name != "test_cli_logs")
