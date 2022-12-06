import atexit
import os
import sys
from typing import TYPE_CHECKING

__all__ = ["logger"]

if TYPE_CHECKING:
    from loguru import logger
else:
    from loguru._logger import Core, Logger

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
        patcher=None,
        extra={},
    )

DEBUG = os.getenv("MM_DEBUG", "0") in ("1", "true", "True", "yes")
DEFAULT_LOG_LEVEL = "DEBUG" if DEBUG else "INFO"


def set_log_level(level: str = DEFAULT_LOG_LEVEL) -> None:
    logger.remove()

    # automatically log to stderr
    if sys.stderr:
        logger.add(sys.stderr, level=level, backtrace=False)

    logger.debug('log level set to "{}"', level)
    # TODO: add file outputs


set_log_level()
atexit.register(logger.remove)
