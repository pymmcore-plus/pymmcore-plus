from __future__ import annotations

import logging
import os
import sys
import time
import weakref
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Iterator

    import pymmcore

__all__ = ["logger"]


logger = logging.getLogger("pymmcore-plus")

# Cores whose primary (CoreLog) log file follows the pymmcore-plus log file.
# See `follow_logfile`.
_CORES: weakref.WeakSet[pymmcore.CMMCore] = weakref.WeakSet()

PYMM_LOG_FILE = os.getenv("PYMM_LOG_FILE", "")
DEFAULT_LOG_LEVEL: str = os.getenv("PYMM_LOG_LEVEL", "WARNING").upper()

if "PYTEST_RUNNING" in os.environ:
    LOG_FILE = None
elif PYMM_LOG_FILE not in ("", "0", "false", "no", "none"):
    LOG_FILE = Path(PYMM_LOG_FILE).expanduser().resolve()
else:
    from ._discovery import USER_DATA_DIR

    LOG_FILE = USER_DATA_DIR / "logs" / "pymmcore-plus.log"


class CustomFormatter(logging.Formatter):
    dark_grey = "\x1b[38;5;240m"
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    _format: str = (
        "%(asctime)s - %(name)s - %(levelname)s - (%(filename)s:%(lineno)d) %(message)s"
    )

    FORMATS: ClassVar[dict[int, str]] = {
        logging.DEBUG: dark_grey + _format + reset,
        logging.INFO: grey + _format + reset,
        logging.WARNING: yellow + _format + reset,
        logging.ERROR: red + _format + reset,
        logging.CRITICAL: bold_red + _format + reset,
    }

    def format(self, record: logging.LogRecord) -> str:
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


_FILE_FORMATTER = logging.Formatter(
    "%(asctime)s.%(msecs)03d    tid0x%(thread)x [%(levelname)s,%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


class _RotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler for a log file that MMCore writes to as well.

    `CMMCorePlus` points the C++ core's own log (the "CoreLog") at the same file
    this handler writes to, via `follow_logfile`, so that Python- and C++-side
    messages interleave in one file. The core keeps its own handle to that file
    open, and on Windows a file cannot be renamed while another handle is open:
    the plain stdlib handler's rollover then fails with ``PermissionError``, drops
    the record, prints a traceback to stderr, and tries again (and fails again) on
    every subsequent record. This handler therefore releases the core's log file
    around the rename and points it at the fresh file afterwards.

    Should the rename still fail (e.g. a second pymmcore-plus process shares the
    default log file), the failure is a soft error: the handler keeps appending to
    the current file, leaves one note in the log, and only retries the rollover
    after ``rollover_retry_interval`` seconds.
    """

    rollover_retry_interval: float = 60.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._next_rollover_attempt = 0.0

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        if time.monotonic() < self._next_rollover_attempt:
            return False
        return bool(super().shouldRollover(record))

    def doRollover(self) -> None:
        # Let go of the file on the C++ side before renaming it (Windows).
        _set_core_logfiles(None)
        try:
            super().doRollover()
        except OSError as exc:
            self._next_rollover_attempt = (
                time.monotonic() + self.rollover_retry_interval
            )
            if self.stream is None:
                self.stream = self._open()
            # Not routed through the logger: emitting from inside a handler would
            # re-enter shouldRollover/doRollover on this same handler.
            self.stream.write(
                f"{time.strftime('%Y-%m-%dT%H:%M:%S')}.000    [WARNING,pymmcore-plus] "
                f"Could not rotate log file {self.baseFilename!r} ({exc}); "
                f"continuing in the current file and retrying in "
                f"{self.rollover_retry_interval:.0f}s\n"
            )
            self.stream.flush()
        finally:
            _set_core_logfiles(Path(self.baseFilename))


def follow_logfile(core: pymmcore.CMMCore) -> Path | None:
    """Write `core`'s own log (the MMCore "CoreLog") into the pymmcore-plus log file.

    The core keeps following the pymmcore-plus log file when that file rotates and
    when `configure_logging` is called again. Returns the current log file, or
    `None` if pymmcore-plus is not logging to a file (the core's primary log file
    is then disabled).
    """
    _CORES.add(core)
    logfile = current_logfile(logger)
    core.setPrimaryLogFile(str(logfile) if logfile else "")
    return logfile


def _set_core_logfiles(file: Path | None) -> None:
    """Point every core registered with `follow_logfile` at `file`.

    If `file` is None, the cores' primary log file is disabled, which closes
    their handle on the previous file.
    """
    for core in list(_CORES):
        core.setPrimaryLogFile(str(file) if file else "")


def configure_logging(
    file: str | Path | None = LOG_FILE,
    stderr_level: int | str = DEFAULT_LOG_LEVEL,
    file_level: int | str = logging.DEBUG,
    log_to_stderr: bool = True,
    file_rotation: int = 40,
    file_retention: int = 20,
) -> None:
    r"""Configure logging for pymmcore-plus.

    This function is called automatically once when pymmcore-plus is imported,
    to set up logging to stderr and a log file.  You can call it again to
    change the logging settings.

    You may also configure logging using the following environment variables:

    - `PYMM_LOG_LEVEL` - The log level for `stderr` logging. By default `INFO`.
    - `PYMM_LOG_FILE` - The path to the log file.  If set to `0`, `false`, `no`,
        or `none`, logging to file will be disabled.
    - `PYMM_LOG_RICH` - If set to `1`, `true`, or `yes`, use `rich` for stderr
        logging (requires `rich` to be installed). Note: rich formatting adds
        some overhead; see https://github.com/pymmcore-plus/pymmcore-plus/issues/449.


    !!! note

        This function will clear all existing logging handlers and replace them
        with new ones.  So be sure to pass all the settings you want to use each
        time you call this function.

    Parameters
    ----------
    file : str | Path | None
        Path to logfile. May also be set with MM_LOG_FILE environment variable.
        If `None`, will not log to file.  By default, logs to:
        Mac OS X:   ~/Library/Application Support/pymmcore-plus/logs
        Unix:       ~/.local/share/pymmcore-plus/logs
        Win:        C:\Users\<username>\AppData\Local\pymmcore-plus\pymmcore-plus\logs
    stderr_level : int | str
        Level for stderr logging.
        One of "TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL",
        or 5, 10, 20, 30, 40, or 50, respectively.
        by default `"INFO"`.
    file_level : int | str
        Level for logging to file, by default `"TRACE"`
    log_to_stderr : bool
        Whether to log to stderr, by default True
    file_rotation : int
        When to rollover to the next log file, in MegaBytes, by default `40`.
    file_retention : int
        Maximum number of log files to retain, by default `20`
    """
    # logging.basicConfig(level=logging.DEBUG)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    # automatically log to stderr
    if log_to_stderr and sys.stderr:
        # use rich for stderr logging if PYMM_LOG_RICH is set and rich is installed
        stderr_handler: logging.Handler | None = None
        if os.getenv("PYMM_LOG_RICH", "").lower() in ("1", "true", "yes"):
            try:
                from rich.logging import RichHandler

                stderr_handler = RichHandler()
            except ImportError:
                pass

        if stderr_handler is None:
            stderr_handler = logging.StreamHandler(sys.stderr)
            stderr_handler.setFormatter(CustomFormatter())

        stderr_handler.setLevel(stderr_level)
        logger.addHandler(stderr_handler)

    # automatically log to file
    if file:
        log_file = Path(file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Create a rotating file handler with a maximum file size and backup count.
        file_handler = _RotatingFileHandler(
            log_file, maxBytes=file_rotation * 1_000_000, backupCount=file_retention
        )
        file_handler.setLevel(file_level)
        file_handler.setFormatter(_FILE_FORMATTER)
        logger.addHandler(file_handler)

    # cores created earlier keep logging into the (possibly new) log file
    _set_core_logfiles(current_logfile(logger))


def current_logfile(logger: logging.Logger) -> Path | None:
    """Return the first RotatingFileHandler's baseFilename."""
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            return Path(handler.baseFilename)
    return None


@contextmanager
def exceptions_logged() -> Iterator[None]:
    """Context manager to log exceptions."""
    try:
        yield
    except Exception as e:
        logger.error(e)


configure_logging()
