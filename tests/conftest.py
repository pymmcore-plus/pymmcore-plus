from __future__ import annotations

import os
import time
from contextlib import contextmanager
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
    from collections.abc import Callable, Iterator

    from pymmcore_plus.core.events._protocol import PSignalInstance

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


class PsygnalBot:
    """Lightweight replacement for qtbot's signal-waiting API."""

    @contextmanager
    def waitSignal(self, signal: PSignalInstance, **kwargs: Any) -> Iterator[None]:
        with self.waitSignals([signal], **kwargs):
            yield

    @contextmanager
    def waitSignals(
        self,
        signals: list[PSignalInstance],
        *,
        timeout: int = 5000,
        check_params_cbs: list[Callable[..., bool]] | None = None,
        order: str | None = None,
    ) -> Iterator[None]:
        received: list[int] = []
        slots: list[Callable] = []
        for i, sig in enumerate(signals):
            pcb = check_params_cbs[i] if check_params_cbs else None

            def _slot(
                *a: Any,
                _i: int = i,
                _pcb: Callable[..., bool] | None = pcb,
            ) -> None:
                if not _pcb or _pcb(*a):
                    received.append(_i)

            slots.append(_slot)
            sig.connect(_slot)
        try:
            yield
        finally:
            self.waitUntil(
                lambda: len(received) >= len(signals),
                timeout=timeout,
            )
            for sig, slot in zip(signals, slots, strict=False):
                sig.disconnect(slot)
            if order == "strict":
                assert received == list(range(len(signals)))

    def waitUntil(self, callback: Callable[[], bool], *, timeout: int = 5000) -> None:
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            if callback():
                return
            time.sleep(0.01)
        raise TimeoutError(f"Condition not met within {timeout}ms")

    @contextmanager
    def capture_exceptions(self) -> Iterator[list]:
        yield []


@pytest.fixture
def anybot(request: pytest.FixtureRequest, core: pymmcore_plus.CMMCorePlus) -> Any:
    if isinstance(core._events, CMMCoreSignaler):
        return PsygnalBot()
    return request.getfixturevalue("qtbot")


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
