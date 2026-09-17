from __future__ import annotations

import gc
import logging
import os
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

import pymmcore_plus._pymmcore as pymmcore
from pymmcore_plus import CMMCorePlus, _logger
from pymmcore_plus._logger import (
    MMCoreHandler,
    _to_mmcore_level,
    configure_logging,
    current_logfile,
    logger,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _wait_for(predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    """MMCore writes log files from a background thread; poll for `predicate`."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _contains(file: Path, text: str) -> Callable[[], bool]:
    return lambda: file.exists() and text in file.read_text()


@pytest.fixture
def debug_logger() -> None:
    """conftest silences the pymmcore-plus logger; let records through here."""
    logger.setLevel(logging.DEBUG)  # restored by conftest's _restore_logger_state


# ----------------------------------------------------------------------------
# level mapping
# ----------------------------------------------------------------------------


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


# ----------------------------------------------------------------------------
# routing of python records into the MMCore log
# ----------------------------------------------------------------------------


def test_log_routed_to_mmcore_file(tmp_path: Path, debug_logger: None) -> None:
    log_file = tmp_path / "routed.log"
    configure_logging(file=log_file, file_level="DEBUG", log_to_stderr=False)

    core = CMMCorePlus()
    assert core.getPrimaryLogFile() == str(log_file)
    assert current_logfile() == log_file

    logger.info("hello from python")
    logger.warning("watch out")
    logger.debug("low-detail trace")
    logger.info("line one\nline two")
    try:
        raise ValueError("kaboom")
    except ValueError:
        logger.exception("something failed")

    assert _wait_for(_contains(log_file, "kaboom"))
    contents = log_file.read_text()
    assert "[IFO,pymmcore-plus] hello from python" in contents
    assert "[WRN,pymmcore-plus] watch out" in contents
    assert "[dbg,pymmcore-plus] low-detail trace" in contents
    # MMCore formats multi-line messages (including tracebacks) as continuation
    # lines, so they stay attached to their record.
    assert "[IFO,pymmcore-plus] line one\n" in contents
    assert "] line two\n" in contents
    assert "[ERR,pymmcore-plus] something failed\n" in contents
    assert "] Traceback (most recent call last):" in contents
    assert "] ValueError: kaboom" in contents


def test_python_and_core_records_are_ordered(
    tmp_path: Path, debug_logger: None
) -> None:
    """Issue #385: python and C++ records used to be written by two independent
    writers and could appear out of order. Through CMMCore.log() there is one
    queue, so file order matches call order."""
    log_file = tmp_path / "ordered.log"
    configure_logging(file=log_file, log_to_stderr=False)
    core = CMMCorePlus()
    for i in range(50):
        core.logMessage(f"msg {i} from core")
        logger.info("info %d from python", i)
    assert _wait_for(_contains(log_file, "info 49 from python"))

    lines = [
        ln
        for ln in log_file.read_text().splitlines()
        if ln.endswith(("core", "python"))
    ]
    expected = [
        f"msg {i} from core" if k == 0 else f"info {i} from python"
        for i in range(50)
        for k in (0, 1)
    ]
    assert [ln.split("] ", 1)[1] for ln in lines] == expected


def test_python_holds_no_file_handle(tmp_path: Path) -> None:
    """The file is written only by MMCore; there is no python-side file handler
    whose open handle could block MMCore's rotation (the PR #630 problem)."""
    configure_logging(file=tmp_path / "x.log", log_to_stderr=False)
    CMMCorePlus()
    assert not any(isinstance(h, logging.FileHandler) for h in logger.handlers)
    assert [type(h) for h in logger.handlers if isinstance(h, MMCoreHandler)] == [
        MMCoreHandler
    ]


def test_rotation_by_mmcore(tmp_path: Path, debug_logger: None) -> None:
    """Rotation is done by MMCore, which owns the only handle on the file, so it
    also works on Windows (where a file cannot be renamed while another handle
    is open). Python records continue in the fresh file afterwards."""
    log_file = tmp_path / "rot.log"
    configure_logging(file=log_file, log_to_stderr=False)
    core = CMMCorePlus()
    # configure_logging() only accepts whole MB; use the core API for a tiny limit
    core.setPrimaryLogFileRotation(3_000, 5)

    for i in range(40):
        logger.info("python message %03d %s", i, "x" * 40)
    # MMCore names backups {stem}_{YYYYMMDD}T{HHMMSS}{ext}
    assert _wait_for(lambda: len(list(tmp_path.glob("rot_*.log"))) == 1)
    (backup,) = tmp_path.glob("rot_*.log")
    assert "python message 000" in backup.read_text()

    # NOTE: MMCore's backup names have 1 s resolution. A second rotation within
    # the same second would rename onto the same backup name, so wait a bit.
    time.sleep(1.1)
    logger.info("after rotation")
    assert _wait_for(_contains(log_file, "after rotation"))
    assert "python message 000" not in log_file.read_text()
    assert core.getPrimaryLogFile() == str(log_file)


# ----------------------------------------------------------------------------
# multiple cores
# ----------------------------------------------------------------------------


def test_records_go_to_newest_live_core(tmp_path: Path, debug_logger: None) -> None:
    """Python records are written by exactly one core: the most recently created
    one that is still alive. When it is garbage collected, records fall back to
    the previous live core instead of being dropped."""
    shared = tmp_path / "shared.log"
    only_a = tmp_path / "only_a.log"
    configure_logging(file=shared, log_to_stderr=False)

    core_a = CMMCorePlus()
    core_a.setPrimaryLogFile(str(only_a))  # divert a's log so we can tell them apart
    core_b = CMMCorePlus()
    assert _logger._handler.core is core_b
    assert _logger._handler.cores == [core_a, core_b]

    logger.info("record while b is alive")
    assert _wait_for(_contains(shared, "record while b is alive"))
    assert "record while b is alive" not in only_a.read_text()

    del core_b
    gc.collect()
    assert _logger._handler.core is core_a
    assert _logger._handler.cores == [core_a]

    logger.info("record after b was collected")
    assert _wait_for(_contains(only_a, "record after b was collected"))
    assert "record after b was collected" not in shared.read_text()


def test_configure_logging_applies_to_all_live_cores(tmp_path: Path) -> None:
    first = tmp_path / "first.log"
    second = tmp_path / "second.log"
    configure_logging(file=first, log_to_stderr=False)
    core_a = CMMCorePlus()
    core_b = CMMCorePlus()
    assert core_a.getPrimaryLogFile() == str(first)
    assert core_b.getPrimaryLogFile() == str(first)

    configure_logging(file=second, log_to_stderr=True, stderr_level="ERROR")
    for core in (core_a, core_b):
        assert core.getPrimaryLogFile() == str(second)
        assert core.stderrLogEnabled()
        assert core.getStderrLogLevel() == pymmcore.LogLevelError

    configure_logging(file=None, log_to_stderr=False)
    for core in (core_a, core_b):
        assert core.getPrimaryLogFile() == ""
        assert not core.stderrLogEnabled()
    assert current_logfile() is None


def test_two_cores_share_one_file(tmp_path: Path) -> None:
    """Two cores each write their own C++ log into the same file through their
    own (append-mode) handle. Without rotation no line is lost or torn."""
    log_file = tmp_path / "shared.log"
    configure_logging(file=log_file, log_to_stderr=False)
    core_a = CMMCorePlus()
    core_b = CMMCorePlus()
    for i in range(200):
        core_a.logMessage(f"CORE-A {i:03d} " + "a" * 60)
        core_b.logMessage(f"CORE-B {i:03d} " + "b" * 60)
    assert _wait_for(_contains(log_file, "CORE-B 199"))
    assert _wait_for(_contains(log_file, "CORE-A 199"))

    lines = log_file.read_text().splitlines()
    a_lines = [ln for ln in lines if "CORE-A" in ln]
    b_lines = [ln for ln in lines if "CORE-B" in ln]
    assert len(a_lines) == len(b_lines) == 200
    assert all(ln.endswith("a" * 60) for ln in a_lines)
    assert all(ln.endswith("b" * 60) for ln in b_lines)


def test_second_core_can_use_its_own_file(tmp_path: Path, debug_logger: None) -> None:
    """MMCore rotation is per core and not coordinated between cores sharing a
    file, so a second core that needs rotation should get its own file. Doing so
    does not affect where python records go (newest live core)."""
    main_log = tmp_path / "main.log"
    other_log = tmp_path / "other.log"
    configure_logging(file=main_log, log_to_stderr=False)
    core_a = CMMCorePlus()
    core_b = CMMCorePlus()
    core_b.setPrimaryLogFile(str(other_log))
    core_b.logMessage("from core b")
    core_a.logMessage("from core a")
    logger.info("from python")
    assert _wait_for(_contains(other_log, "from python"))
    assert _wait_for(_contains(main_log, "from core a"))
    assert "from core b" not in main_log.read_text()
    assert "from python" not in main_log.read_text()


# ----------------------------------------------------------------------------
# no core (yet / any more)
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env_value, expect_file",
    [("", True), ("none", False), ("0", False), ("custom.log", True)],
)
def test_pymm_log_file_env_var(
    tmp_path: Path, env_value: str, expect_file: bool
) -> None:
    """PYMM_LOG_FILE is read once at import time (in a fresh interpreter)."""
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_RUNNING"}
    if env_value == "custom.log":
        env_value = str(tmp_path / "custom.log")
    env["PYMM_LOG_FILE"] = env_value
    code = "from pymmcore_plus._logger import LOG_FILE; print(repr(LOG_FILE))"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stderr
    if not expect_file:
        assert result.stdout.strip() == "None"
    elif env_value:
        assert result.stdout.strip() == repr(tmp_path / "custom.log")
    else:
        assert "pymmcore-plus.log" in result.stdout


def test_records_before_any_core_use_last_resort() -> None:
    """Before a CMMCorePlus exists no handler is installed: WARNING+ records reach
    stderr through logging.lastResort, lower levels are dropped."""
    code = (
        "import logging, pymmcore_plus\n"
        "log = logging.getLogger('pymmcore-plus')\n"
        "assert not log.handlers, log.handlers\n"
        "log.warning('pre-core warning')\n"
        "log.info('pre-core info')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert "pre-core warning" in result.stderr
    assert "pre-core info" not in result.stderr


def test_records_after_all_cores_collected_use_last_resort(
    tmp_path: Path, debug_logger: None, capsys: pytest.CaptureFixture
) -> None:
    configure_logging(file=tmp_path / "x.log", log_to_stderr=False)
    core = CMMCorePlus()
    assert _logger._handler in logger.handlers
    del core
    gc.collect()
    _logger._handler._cores.clear()  # in case other tests' cores are still alive
    assert _logger._handler.core is None

    logger.warning("orphan warning")
    logger.info("orphan info")
    err = capsys.readouterr().err
    assert "orphan warning" in err
    assert "orphan info" not in err


def test_configure_logging_before_core_is_applied_on_creation(tmp_path: Path) -> None:
    _logger._handler._cores.clear()
    log_file = tmp_path / "early.log"
    configure_logging(
        file=log_file,
        stderr_level="ERROR",
        file_level="INFO",
        log_to_stderr=False,
        file_rotation=3,
        file_retention=2,
    )
    core = CMMCorePlus()
    assert core.getPrimaryLogFile() == str(log_file)
    assert core.getPrimaryLogLevel() == pymmcore.LogLevelInfo
    assert core.getStderrLogLevel() == pymmcore.LogLevelError
    assert not core.stderrLogEnabled()
    assert _wait_for(log_file.exists)


# ----------------------------------------------------------------------------
# configuration details
# ----------------------------------------------------------------------------


def test_default_config_matches_old_defaults() -> None:
    core = CMMCorePlus()
    assert core.getPrimaryLogLevel() == pymmcore.LogLevelDebug
    assert core.getStderrLogLevel() == pymmcore.LogLevelWarning
    assert core.stderrLogEnabled() is True


def test_stderr_output_via_mmcore(
    tmp_path: Path, debug_logger: None, capfd: pytest.CaptureFixture
) -> None:
    configure_logging(file=None, log_to_stderr=True, stderr_level="WARNING")
    CMMCorePlus()
    logger.warning("py warning to stderr")
    logger.info("py info not to stderr")
    assert _wait_for(lambda: "py warning to stderr" in capfd.readouterr().err)
    # NB: capfd.readouterr() consumes; the info line must never have appeared
    time.sleep(0.1)
    assert "py info not to stderr" not in capfd.readouterr().err


def test_attach_core_sets_levels(tmp_path: Path) -> None:
    configure_logging(
        file=tmp_path / "lvl.log",
        stderr_level="ERROR",
        file_level="DEBUG",
        log_to_stderr=False,
    )
    core = CMMCorePlus()
    assert core.getPrimaryLogLevel() == pymmcore.LogLevelDebug
    assert core.getStderrLogLevel() == pymmcore.LogLevelError
    assert not core.stderrLogEnabled()


def test_configure_logging_replaces_manual_core_settings(tmp_path: Path) -> None:
    """Settings made directly on the core are overwritten by configure_logging()."""
    configure_logging(file=None, log_to_stderr=False)
    core = CMMCorePlus()
    core.setPrimaryLogFile(str(tmp_path / "manual.log"))
    core.enableStderrLog(True)
    configure_logging(file=None, log_to_stderr=False)
    assert core.getPrimaryLogFile() == ""
    assert not core.stderrLogEnabled()


def test_unwritable_log_file_warns_and_disables_file(tmp_path: Path) -> None:
    """A log file that cannot be opened (here: a directory) must not make
    CMMCorePlus() fail; file logging is disabled for that core with a warning."""
    configure_logging(file=tmp_path, log_to_stderr=False)
    with pytest.warns(RuntimeWarning, match="could not open log file"):
        core = CMMCorePlus()
    assert core.getPrimaryLogFile() == ""
    assert not core.stderrLogEnabled()


def test_handler_survives_core_failure(debug_logger: None) -> None:
    """core.log() errors are reported via Handler.handleError, not raised."""
    _logger._handler._cores.clear()

    class BadCore:
        def log(self, *args: object) -> None:
            raise RuntimeError("core gone")

    bad = BadCore()
    _logger._handler.attach(bad)  # type: ignore[arg-type]
    if _logger._handler not in logger.handlers:
        logger.addHandler(_logger._handler)
    errors: list[logging.LogRecord] = []
    _logger._handler.handleError = errors.append  # type: ignore[method-assign]
    try:
        logger.warning("this is fine")
    finally:
        del _logger._handler.handleError
    assert len(errors) == 1
    assert errors[0].getMessage() == "this is fine"


def test_current_logfile_accepts_deprecated_logger_arg(tmp_path: Path) -> None:
    configure_logging(file=tmp_path / "cl.log")
    assert current_logfile(logger) == tmp_path / "cl.log"
    assert current_logfile() == tmp_path / "cl.log"
