"""Internal module to choose between pymmcore and pymmcore-nano."""

import re
from typing import NamedTuple

try:
    from pymmcore_nano import *  # noqa F403
    from pymmcore_nano import __version__

    BACKEND = "pymmcore-nano"
    NANO = True
except ImportError:
    from pymmcore import *  # noqa F403
    from pymmcore import __version__

    BACKEND = "pymmcore"
    NANO = False


class VersionInfo(NamedTuple):
    """Version info for the backend."""

    major: int
    minor: int
    micro: int
    device_interface: int
    build: int = 0


# pass no more than 5 parts to VersionInfo
numbers = re.findall(r"\d+", __version__)[:5]
version_info = VersionInfo(*(int(i) for i in numbers))
