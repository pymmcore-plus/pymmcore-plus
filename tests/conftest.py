from __future__ import annotations

import os
from unittest.mock import patch

import pymmcore_plus._pymmcore

os.environ["PYTEST_RUNNING"] = "1"
from typing import TYPE_CHECKING, Any

import pytest

import pymmcore_plus
from pymmcore_plus._logger import logger
from pymmcore_plus.core.events import CMMCoreSignaler
from pymmcore_plus.mda.events import MDASignaler

if TYPE_CHECKING:
    from collections.abc import Iterator

try:
    from pymmcore_plus.core.events import QCoreSignaler
    from pymmcore_plus.mda.events import QMDASignaler

    PARAMS = ["qt", "psygnal"]
except ImportError:
    PARAMS = ["psygnal"]

logger.setLevel("CRITICAL")


@pytest.fixture(params=PARAMS, scope="function")
def core(
    request: Any, monkeypatch: pytest.MonkeyPatch
) -> Iterator[pymmcore_plus.CMMCorePlus]:
    monkeypatch.setenv("PYMM_SIGNALS_BACKEND", request.param)
    core = pymmcore_plus.CMMCorePlus()
    core.mda.engine.use_hardware_sequencing = False
    if request.param == "psygnal":
        assert isinstance(core._events, CMMCoreSignaler)
        assert isinstance(core.mda._signals, MDASignaler)
    else:
        assert isinstance(core._events, QCoreSignaler)
        assert isinstance(core.mda._signals, QMDASignaler)
    if not core.getDeviceAdapterSearchPaths():
        pytest.fail("To run tests, please install MM with `mmcore install`")
    core.loadSystemConfiguration()
    yield core
    core.__del__()


@pytest.fixture
def mock_fullfocus(core: pymmcore_plus.CMMCorePlus) -> Iterator[None]:
    def _fullfocus():
        core.setZPosition(core.getZPosition() + 50)

    with patch.object(core, "fullFocus", _fullfocus):
        yield


@pytest.fixture
def mock_fullfocus_failure(core: pymmcore_plus.CMMCorePlus) -> Iterator[None]:
    def _fullfocus():
        raise RuntimeError()

    with patch.object(core, "fullFocus", _fullfocus):
        yield


@pytest.fixture
def caplog(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def pytest_collection_modifyitems(session, config, items):
    last_items = []
    first_items = []
    other_items = []
    for item in items:
        if "run_last" in item.keywords:
            last_items.append(item)
        elif "run_first" in item.keywords:
            first_items.append(item)
        else:
            other_items.append(item)
    items[:] = first_items + other_items + last_items


# requires psutil
# @pytest.fixture(autouse=True)
# def monitor_file_descriptors():
#     import psutil

#     process = psutil.Process(os.getpid())
#     before_fds = process.num_fds()

#     yield

#     if _mmcore_plus._instance:
#         _mmcore_plus._instance.__del__()
#         _mmcore_plus._instance = None

#     after_fds = process.num_fds()
#     if after_fds > before_fds:
#         print(f"File descriptors leaked: {after_fds} > {before_fds}")
