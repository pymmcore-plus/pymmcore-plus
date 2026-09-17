from __future__ import annotations

import logging
import os
import warnings
import weakref
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pymmcore_plus._pymmcore as pymmcore

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["MMCoreHandler", "configure_logging", "logger"]


logger = logging.getLogger("pymmcore-plus")
# All records pass to the handler; MMCore enforces the actual thresholds.
logger.setLevel(logging.DEBUG)

PYMM_LOG_FILE = os.getenv("PYMM_LOG_FILE", "")
DEFAULT_LOG_LEVEL: str = os.getenv("PYMM_LOG_LEVEL", "WARNING").upper()

LOG_FILE: Path | None
if "PYTEST_RUNNING" in os.environ or PYMM_LOG_FILE.lower() in (
    "0",
    "false",
    "no",
    "none",
):
    LOG_FILE = None
elif PYMM_LOG_FILE:
    LOG_FILE = Path(PYMM_LOG_FILE).expanduser().resolve()
else:
    from ._discovery import USER_DATA_DIR

    LOG_FILE = USER_DATA_DIR / "logs" / "pymmcore-plus.log"


_NAME_TO_MM: dict[str, int] = {
    "TRACE": pymmcore.LogLevelTrace,
    "DEBUG": pymmcore.LogLevelDebug,
    "INFO": pymmcore.LogLevelInfo,
    "WARNING": pymmcore.LogLevelWarning,
    "ERROR": pymmcore.LogLevelError,
    "CRITICAL": pymmcore.LogLevelCritical,
}


def _to_mmcore_level(level: int | str) -> int:
    """Convert a Python logging level (int or name) to an MMCore log level int."""
    if isinstance(level, str):
        upper = level.upper()
        if upper in _NAME_TO_MM:
            return _NAME_TO_MM[upper]
        try:
            level = int(level)
        except ValueError as e:
            raise ValueError(f"Unknown log level: {level!r}") from e
    n = int(level)
    if n < logging.DEBUG:
        return pymmcore.LogLevelTrace
    if n < logging.INFO:
        return pymmcore.LogLevelDebug
    if n < logging.WARNING:
        return pymmcore.LogLevelInfo
    if n < logging.ERROR:
        return pymmcore.LogLevelWarning
    if n < logging.CRITICAL:
        return pymmcore.LogLevelError
    return pymmcore.LogLevelCritical


@dataclass(frozen=True)
class _LogConfig:
    file: Path | None
    stderr_level: int | str
    file_level: int | str
    log_to_stderr: bool
    file_rotation: int  # MB
    file_retention: int


_config: _LogConfig = _LogConfig(
    file=LOG_FILE,
    stderr_level=DEFAULT_LOG_LEVEL,
    file_level=logging.DEBUG,
    log_to_stderr=True,
    file_rotation=40,
    file_retention=20,
)


class MMCoreHandler(logging.Handler):
    """Logging handler that forwards Python log records to ``CMMCore.log()``.

    Every :class:`~pymmcore_plus.CMMCorePlus` registers itself with the single
    module-level instance of this handler (see :func:`_attach_core`).  Cores are
    held weakly.  A record is forwarded to the *most recently created* core that
    is still alive, so that

    - with several cores in one process, Python records are written exactly once
      (they are not duplicated into every core's log), and
    - when the newest core is garbage collected, records fall back to the next
      most recent live core instead of being dropped.

    If no core is alive at all, WARNING+ records are passed to
    ``logging.lastResort`` (stderr), which is exactly what the ``logging`` module
    would do if this handler were not installed.
    """

    def __init__(self) -> None:
        super().__init__()
        # weak references to registered cores, oldest first
        self._cores: list[weakref.ref[pymmcore.CMMCore]] = []
        # MMCore prepends timestamp/thread/level/name itself.
        self.setFormatter(logging.Formatter("%(message)s"))

    def attach(self, core: pymmcore.CMMCore) -> None:
        """Register `core` as the (new) destination for Python log records."""
        with self.lock:  # type: ignore[union-attr]
            self._cores = [
                r for r in self._cores if (c := r()) is not None and c is not core
            ]
            self._cores.append(weakref.ref(core))

    @property
    def cores(self) -> list[pymmcore.CMMCore]:
        """All registered cores that are still alive, oldest first."""
        return [core for ref in self._cores if (core := ref()) is not None]

    @property
    def core(self) -> pymmcore.CMMCore | None:
        """The core that currently receives Python log records, if any."""
        for ref in reversed(self._cores):
            if (core := ref()) is not None:
                return core
        return None

    def emit(self, record: logging.LogRecord) -> None:
        core = self.core
        if core is None:
            # mimic Logger.callHandlers: handler level check, then handle()
            last_resort = logging.lastResort
            if last_resort is not None and record.levelno >= last_resort.level:
                last_resort.handle(record)
            return
        try:
            msg = self.format(record)
            mm_level = _to_mmcore_level(record.levelno)
            core.log(msg, mm_level, record.name)
        except Exception:
            self.handleError(record)


# The single handler forwarding `logger` records to MMCore. It is added to `logger`
# the first time a CMMCorePlus is created (see `_attach_core`).
_handler = MMCoreHandler()


def _apply_config_to_core(core: pymmcore.CMMCore) -> None:
    """Push the current ``_config`` to ``core``."""
    cfg = _config
    if cfg.file is not None:
        try:
            Path(cfg.file).parent.mkdir(parents=True, exist_ok=True)
            core.setPrimaryLogFile(str(cfg.file))
        except Exception as e:
            # Don't make the core unusable just because the log file is not
            # writable (e.g. a bad PYMM_LOG_FILE or a read-only log directory).
            core.setPrimaryLogFile("")
            warnings.warn(
                f"pymmcore-plus could not open log file {str(cfg.file)!r}: {e}. "
                "Logging to file is disabled for this core.",
                RuntimeWarning,
                stacklevel=3,
            )
    else:
        core.setPrimaryLogFile("")
    core.setPrimaryLogFileRotation(cfg.file_rotation * 1_000_000, cfg.file_retention)
    core.setPrimaryLogLevel(_to_mmcore_level(cfg.file_level))
    core.setStderrLogLevel(_to_mmcore_level(cfg.stderr_level))
    core.enableStderrLog(cfg.log_to_stderr)


def configure_logging(
    file: str | Path | None = LOG_FILE,
    stderr_level: int | str = DEFAULT_LOG_LEVEL,
    file_level: int | str = logging.DEBUG,
    log_to_stderr: bool = True,
    file_rotation: int = 40,
    file_retention: int = 20,
) -> None:
    r"""Configure logging for pymmcore-plus.

    All Python logs from the ``pymmcore-plus`` logger are forwarded to MMCore,
    which is the single sink: it writes to the primary log file and (optionally)
    to stderr, applying its own level thresholds for each.

    Python logging is left unconfigured until a
    :class:`~pymmcore_plus.CMMCorePlus` is instantiated. Records emitted before
    that point (or after every core has been garbage collected) fall through to
    Python's standard ``lastResort`` handler (WARNING+ to stderr, unformatted).
    Applications that want richer pre-core output should attach their own
    handler to ``logging.getLogger('pymmcore-plus')``.

    With several cores in one process, Python records are forwarded to the most
    recently created core that is still alive (never to more than one, so they
    are not duplicated). Every core writes its own C++ log through its own file
    handle; all of them are given the same file, rotation, and level settings by
    this function. Note that MMCore's log rotation is not coordinated between
    cores (or between processes) sharing one file; give additional cores their
    own file with ``core.setPrimaryLogFile()`` if you rely on rotation.

    Calling this function does not change the level of the ``pymmcore-plus``
    Python logger; the caller controls Python-side filtering, while MMCore
    enforces the file and stderr thresholds independently.

    Settings are applied to the underlying core every time a
    :class:`~pymmcore_plus.CMMCorePlus` is instantiated (and immediately to
    every core that already exists). Module-level defaults match the pre-refactor Python
    handler defaults (file at DEBUG, stderr at WARNING, rotation 40 MB / 20
    files, stderr enabled).

    ``stderr_level`` is the *threshold* MMCore applies when stderr logging is
    enabled; it does not enable stderr by itself. Stderr output is controlled
    by ``log_to_stderr`` (and may be forced on via ``PYMM_STDERR_LOG=1`` or
    ``core.enableStderrLog(True)``).

    You may also configure logging using the following environment variables,
    which are read once at ``pymmcore_plus._logger`` import time only;
    setting them after import has no effect (use ``configure_logging()``
    instead):

    - `PYMM_LOG_LEVEL` - Threshold for **stderr** logging. By default `WARNING`.
    - `PYMM_LOG_FILE` - Path to the log file. If set to `0`, `false`, `no`, or
      `none`, file logging is disabled.

    Parameters
    ----------
    file : str | Path | None
        Path to the primary log file. May also be set with the `PYMM_LOG_FILE`
        environment variable. If `None`, file logging is disabled. By default,
        logs to:

        Mac OS X:   ~/Library/Application Support/pymmcore-plus/logs
        Unix:       ~/.local/share/pymmcore-plus/logs
        Win:        C:\Users\<username>\AppData\Local\pymmcore-plus\pymmcore-plus\logs
    stderr_level : int | str
        Level threshold for stderr logging. One of "TRACE", "DEBUG", "INFO",
        "WARNING", "ERROR", "CRITICAL". By default `"WARNING"` (or
        `PYMM_LOG_LEVEL`). Note that this only sets the threshold; whether
        MMCore writes to stderr is controlled separately by
        ``PYMM_STDERR_LOG`` or ``core.enableStderrLog()``.
    file_level : int | str
        Level threshold for the primary log file. By default `"DEBUG"`.
    log_to_stderr : bool
        Whether MMCore writes log records to stderr. Default ``True``.
        ``PYMM_STDERR_LOG=1`` (read in ``CMMCorePlus.__init__``) overrides
        this to ``True`` after ``configure_logging`` is applied.
    file_rotation : int
        Roll over to the next log file at this size, in MB. By default `40`.
    file_retention : int
        Maximum number of log files to retain. By default `20`.
    """
    global _config
    _config = _LogConfig(
        file=Path(file) if file else None,
        stderr_level=stderr_level,
        file_level=file_level,
        log_to_stderr=log_to_stderr,
        file_rotation=file_rotation,
        file_retention=file_retention,
    )

    for core in _handler.cores:
        _apply_config_to_core(core)


def _attach_core(core: pymmcore.CMMCore) -> None:
    """Register ``core`` with the module-level :class:`MMCoreHandler`.

    Called from ``CMMCorePlus.__init__``. The handler is added to ``logger`` on
    first use, and ``core`` becomes the destination for Python log records (see
    :class:`MMCoreHandler` for what happens with several cores). The current
    :func:`configure_logging` settings are then pushed to ``core``, intentionally
    overwriting whatever was previously set on it (file path, rotation, file
    level, stderr level, stderr enable).
    """
    if _handler not in logger.handlers:
        logger.addHandler(_handler)
    _handler.attach(core)
    _apply_config_to_core(core)


def current_logfile(logger: logging.Logger | None = None) -> Path | None:
    """Return the configured primary log file path, if any.

    .. deprecated:: 0.19
        The ``logger`` parameter is unused and will be removed in a future
        release. Call ``current_logfile()`` with no arguments.
    """
    return _config.file


@contextmanager
def exceptions_logged() -> Iterator[None]:
    """Context manager to log exceptions."""
    try:
        yield
    except Exception as e:
        logger.error(e)
