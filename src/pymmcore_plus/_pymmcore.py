"""Internal module to choose between pymmcore and pymmcore-nano."""

try:
    from pymmcore_nano import *  # noqa F403
    from pymmcore_nano import __version__

    BACKEND = "pymmcore-nano"
except ImportError:
    from pymmcore import *  # noqa F403
    from pymmcore import __version__  # noqa F401

    BACKEND = "pymmcore"
