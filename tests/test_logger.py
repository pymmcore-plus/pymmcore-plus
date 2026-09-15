from __future__ import annotations

import logging
import time
import weakref
from typing import TYPE_CHECKING

import pytest

import pymmcore_plus._pymmcore as pymmcore
from pymmcore_plus import CMMCorePlus
from pymmcore_plus._logger import (
    MMCoreHandler,
    _to_mmcore_level,
    configure_logging,
    logger,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_to_mmcore_level() -> None:
    assert _to_mmcore_level("DEBUG") == pymmcore.LogLevelDebug
    assert _to_mmcore_level("info") == pymmcore.LogLevelInfo
    assert _to_mmcore_level("WARNING") == pymmcore.LogLevelWarning
    assert _to_mmcore_level("Error") == pymmcore.LogLevelError
    assert _to_mmcore_level("CRITICAL") == pymmcore.LogLevelCritical
    assert _to_mmcore_level("TRACE") == pymmcore.LogLevelTrace
    assert _to_mmcore_level(logging.DEBUG) == pymmcore.LogLevelDebug
    assert _to_mmcore_level(logging.INFO) == pymmcore.LogLevelInfo
    assert _to_mmcore_level(5) == pymmcore.LogLevelTrace  # python TRACE
    assert _to_mmcore_level("10") == pymmcore.LogLevelDebug
    assert _to_mmcore_level(25) == pymmcore.LogLevelInfo
    assert _to_mmcore_level(35) == pymmcore.LogLevelWarning
    assert _to_mmcore_level(0) == pymmcore.LogLevelTrace
    assert _to_mmcore_level(100) == pymmcore.LogLevelCritical
    with pytest.raises(ValueError):
        _to_mmcore_level("BOGUS")


def test_attach_core_replaces_handler(tmp_path: Path) -> None:
    log_file = tmp_path / "a.log"
    configure_logging(file=log_file)
    CMMCorePlus()
    assert sum(isinstance(h, MMCoreHandler) for h in logger.handlers) == 1

    c2 = CMMCorePlus()
    mm_handlers = [h for h in logger.handlers if isinstance(h, MMCoreHandler)]
    assert len(mm_handlers) == 1
    # Most recently created core gets the handler.
    assert mm_handlers[0]._core_ref() is c2


def test_log_routed_to_mmcore_file(tmp_path: Path) -> None:
    log_file = tmp_path / "routed.log"
    configure_logging(file=log_file, file_level="DEBUG", log_to_stderr=False)
    logger.setLevel(logging.DEBUG)

    core = CMMCorePlus()
    assert core.getPrimaryLogFile() == str(log_file)

    logger.info("hello from python")
    logger.warning("watch out")
    logger.debug("low-detail trace")
    time.sleep(0.2)

    contents = log_file.read_text().lower()
    assert "[ifo,pymmcore-plus] hello from python" in contents
    assert "[wrn,pymmcore-plus] watch out" in contents
    assert "[dbg,pymmcore-plus] low-detail trace" in contents


def test_configure_logging_updates_attached_core(tmp_path: Path) -> None:
    first = tmp_path / "first.log"
    second = tmp_path / "second.log"
    configure_logging(file=first)
    core = CMMCorePlus()
    assert core.getPrimaryLogFile() == str(first)

    configure_logging(file=second)
    assert core.getPrimaryLogFile() == str(second)


def test_handler_holds_weakref(tmp_path: Path) -> None:
    log_file = tmp_path / "weak.log"
    configure_logging(file=log_file)
    core = CMMCorePlus()
    handler = next(h for h in logger.handlers if isinstance(h, MMCoreHandler))
    assert handler._core_ref() is core
    assert isinstance(handler._core_ref, weakref.ref)


def test_attach_core_sets_levels(tmp_path: Path) -> None:
    log_file = tmp_path / "lvl.log"
    configure_logging(
        file=log_file,
        stderr_level="ERROR",
        file_level="DEBUG",
        log_to_stderr=False,
    )
    core = CMMCorePlus()
    assert core.getPrimaryLogLevel() == pymmcore.LogLevelDebug
    assert core.getStderrLogLevel() == pymmcore.LogLevelError
    assert not core.stderrLogEnabled()


def test_default_config_matches_old_defaults() -> None:
    core = CMMCorePlus()
    assert core.getPrimaryLogLevel() == pymmcore.LogLevelDebug
    assert core.getStderrLogLevel() == pymmcore.LogLevelWarning
    assert core.stderrLogEnabled() is True


def test_configure_logging_log_to_stderr_false_disables(tmp_path: Path) -> None:
    configure_logging(file=tmp_path / "x.log", log_to_stderr=False)
    core = CMMCorePlus()
    assert not core.stderrLogEnabled()


def test_configure_logging_file_none_clears_path(tmp_path: Path) -> None:
    configure_logging(file=tmp_path / "x.log")
    core = CMMCorePlus()
    assert core.getPrimaryLogFile() == str(tmp_path / "x.log")
    configure_logging(file=None)
    assert core.getPrimaryLogFile() == ""
