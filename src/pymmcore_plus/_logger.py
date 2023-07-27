from __future__ import annotations

import atexit
import contextlib
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

try:
    from typing_extensions import deprecated
except ImportError:

    def deprecated(*args, **kwargs):  # type: ignore
        def _decorator(func):  # type: ignore
            return func

        return _decorator


__all__ = ["logger"]

if TYPE_CHECKING:
    from loguru import logger
    from typing_extensions import Literal

    LogLvlStr = Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    LogLvlInt = Literal[5, 10, 20, 30, 40, 50]
else:
    from loguru import __version__
    from loguru._logger import Core, Logger

    PATCHERS = {"patchers": []}
    with contextlib.suppress(Exception):
        if tuple(int(x) for x in __version__.split("."))[:2] < (0, 7):
            PATCHERS = {"patcher": None}

    # avoid using the global loguru logger in case other packages are using it.
    logger = Logger(
        core=Core(),
        exception=None,
        depth=0,
        record=False,
        lazy=False,
        colors=False,
        raw=False,
        capture=True,
        extra={},
        **PATCHERS,
    )

DEBUG: bool = os.getenv("MM_DEBUG", "0") in ("1", "true", "True", "yes")
DEFAULT_LOG_LEVEL: LogLvlStr = "DEBUG" if DEBUG else "INFO"
if "MM_LOG_FILE" in os.environ:
    if os.environ["MM_LOG_FILE"].lower() in ("", "0", "false", "no", "none"):
        LOG_FILE = None
    else:
        LOG_FILE = Path(os.environ["MM_LOG_FILE"]).expanduser().resolve()
else:
    from ._util import USER_DATA_DIR

    LOG_FILE = USER_DATA_DIR / "logs" / "pymmcore-plus.log"


def configure_logging(
    file: str | Path | None = LOG_FILE,
    strerr_level: LogLvlStr | LogLvlInt = DEFAULT_LOG_LEVEL,
    file_level: LogLvlStr | LogLvlInt = "TRACE",
    log_to_stderr: bool = True,
    file_rotation: str = "40MB",
    file_retention: int = 20,
) -> None:
    r"""Configure logging for pymmcore-plus.

    Parameters
    ----------
    file : str | Path | None, optional
        Path to logfile. May also be set with MM_LOG_FILE environment variable.
        If `None`, will not log to file.  By default, logs to:
        Mac OS X:   ~/Library/Application Support/pymmcore-plus/logs
        Unix:       ~/.local/share/pymmcore-plus/logs
        Win:        C:\Users\<username>\AppData\Local\pymmcore-plus\pymmcore-plus\logs
    strerr_level : LogLvlStr | LogLvlInt, optional
        Level for stderr logging.
        One of "TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL",
        by default DEBUG.
    file_level : LogLvlStr | LogLvlInt, optional
        Level for logging to file, by default "TRACE"
    log_to_stderr : bool, optional
        Whether to log to stderr, by default True
    file_rotation : str, optional
        When to rollover to the next log file, by default "40MB"
    file_retention : int, optional
        Maximum number of log files to retain, by default 20
    """
    logger.remove()

    # automatically log to stderr
    if log_to_stderr and sys.stderr:
        logger.add(sys.stderr, level=strerr_level, backtrace=False)

    # automatically log to file
    if file:
        log_file = Path(file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_file,
            level=file_level,
            backtrace=False,
            enqueue=True,
            rotation=file_rotation,
            retention=file_retention,
        )


@deprecated("Use configure_logging instead.")
def set_log_level(level: LogLvlStr | LogLvlInt = DEFAULT_LOG_LEVEL) -> None:
    import warnings

    warnings.warn(
        "set_log_level is deprecated. Use configure_logging instead.",
        FutureWarning,
        stacklevel=1,
    )
    configure_logging(strerr_level=level)


configure_logging()
atexit.register(logger.remove)
