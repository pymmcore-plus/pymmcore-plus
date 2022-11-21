import sys

sys.stderr.write(
    """
===============================
Unsupported installation method
===============================
pymmcore-plus does not support installation with `python setup.py install`.
Please use `python -m pip install .` instead.
"""
)
sys.exit(1)


# The below code will never execute, however GitHub is particularly
# picky about where it finds Python packaging metadata.
# See: https://github.com/github/feedback/discussions/6456
#
# To be removed once GitHub catches up.

setup(  # noqa
    name="pymmcore-plus",
    install_requires=[
        "loguru",
        "numpy",
        "psygnal>=0.4.2",
        "pymmcore>=10.1.1.70.4",
        "typing-extensions",
        "useq-schema",
        "wrapt",
    ],
)
