from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import pytest

from pymmcore_plus import CMMCorePlus, _logger

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def pymm_logfile(tmp_path: Path) -> Iterator[Path]:
    """Configure pymmcore-plus to log to a small rotating file in tmp_path."""
    log_file = tmp_path / "pymmcore-plus.log"
    _logger.configure_logging(file=log_file, log_to_stderr=False)
    handler = _logger.logger.handlers[0]
    assert isinstance(handler, _logger._RotatingFileHandler)
    handler.maxBytes = 2_000
    # conftest silences the pymmcore-plus logger; records must reach the file here
    level = _logger.logger.level
    _logger.logger.setLevel(logging.DEBUG)
    try:
        yield log_file
    finally:
        _logger.logger.setLevel(level)
        # also releases the core's handle on the file so tmp_path can be removed
        _logger.configure_logging(file=None, log_to_stderr=False)


def _wait_for(predicate, timeout: float = 2.0) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def test_core_log_follows_rotation(pymm_logfile: Path) -> None:
    """The C++ core logs to the same file as the Python logger. On Windows its open
    handle used to make every rollover fail with PermissionError; rotation must
    succeed and the core must carry on in the fresh file."""
    core = CMMCorePlus()
    assert core.getPrimaryLogFile() == str(pymm_logfile)
    assert _logger.current_logfile(_logger.logger) == pymm_logfile

    core.logMessage("core message before rotation")
    assert _wait_for(lambda: "core message before rotation" in pymm_logfile.read_text())

    for i in range(100):
        _logger.logger.info("python message %03d %s", i, "x" * 40)

    rotated = pymm_logfile.with_name("pymmcore-plus.log.1")
    assert rotated.exists(), "log file did not rotate"
    assert "core message before rotation" not in pymm_logfile.read_text()

    # the core followed the rotation and writes into the new file
    assert core.getPrimaryLogFile() == str(pymm_logfile)
    core.logMessage("core message after rotation")
    assert _wait_for(lambda: "core message after rotation" in pymm_logfile.read_text())
    assert "python message 099" in pymm_logfile.read_text()


def test_core_log_follows_configure_logging(tmp_path: Path) -> None:
    first = tmp_path / "first.log"
    second = tmp_path / "second.log"
    _logger.configure_logging(file=first, log_to_stderr=False)
    try:
        core = CMMCorePlus()
        assert core.getPrimaryLogFile() == str(first)

        _logger.configure_logging(file=second, log_to_stderr=False)
        assert core.getPrimaryLogFile() == str(second)

        _logger.configure_logging(file=None, log_to_stderr=False)
        assert core.getPrimaryLogFile() == ""
        # nothing holds the files any more
        first.rename(tmp_path / "first.moved")
    finally:
        _logger.configure_logging(file=None, log_to_stderr=False)


def test_failed_rollover_keeps_logging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A rollover that still fails (e.g. another process holds the file open on
    Windows) must not drop records or spam stderr, and must be retried later."""
    log_file = tmp_path / "test.log"
    handler = _logger._RotatingFileHandler(log_file, maxBytes=200, backupCount=3)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log = logging.getLogger("test-failed-rollover")
    log.propagate = False
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)

    attempts = 0

    def failing_rotate(source: str, dest: str) -> None:
        nonlocal attempts
        attempts += 1
        raise PermissionError(32, "The process cannot access the file", source)

    monkeypatch.setattr(handler, "rotate", failing_rotate)

    try:
        for i in range(50):
            log.info("message %03d %s", i, "x" * 20)
        handler.flush()

        content = log_file.read_text()
        # every record was written, to the original file
        for i in range(50):
            assert f"message {i:03d}" in content
        assert not (tmp_path / "test.log.1").exists()
        # the failure is noted in the log itself ...
        assert content.count("Could not rotate log file") == 1
        # ... only tried once thanks to the retry back-off ...
        assert attempts == 1
        # ... and nothing was printed via Handler.handleError
        assert capsys.readouterr().err == ""

        # once the retry interval has passed and the file is free, rotation resumes
        handler._next_rollover_attempt = 0.0
        monkeypatch.undo()
        log.info("after the other process released the file %s", "y" * 200)
        log.info("first record in the fresh file")
        handler.flush()
        assert (tmp_path / "test.log.1").exists()
        assert "first record in the fresh file" in log_file.read_text()
    finally:
        log.removeHandler(handler)
        handler.close()
