# pymmcore-plus

[![License](https://img.shields.io/pypi/l/pymmcore-plus.svg?color=green)](https://github.com/pymmcore-plus/pymmcore-plus/raw/master/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/pymmcore-plus.svg?color=green)](https://pypi.org/project/pymmcore-plus)
[![Python
Version](https://img.shields.io/pypi/pyversions/pymmcore-plus.svg?color=green)](https://python.org)
[![CI](https://github.com/pymmcore-plus/pymmcore-plus/actions/workflows/test_and_deploy.yml/badge.svg)](https://github.com/pymmcore-plus/pymmcore-plus/actions/workflows/test_and_deploy.yml)
[![codecov](https://codecov.io/gh/pymmcore-plus/pymmcore-plus/branch/main/graph/badge.svg)](https://codecov.io/gh/pymmcore-plus/pymmcore-plus)

`pymmcore-plus` extends [pymmcore](https://github.com/micro-manager/pymmcore)
(python bindings for the C++ [micro-manager
core](https://github.com/micro-manager/mmCoreAndDevices/)) with a number of
features designed to facilitate working with **Micro-manager in pure python/C
environments**.

- `pymmcore_plus.CMMCorePlus` is a drop-in replacement subclass of
  `pymmcore.CMMCore` that provides a number of helpful overrides and additional
  convenience functions beyond the standard [CMMCore
  API](https://javadoc.scijava.org/Micro-Manager-Core/mmcorej/CMMCore.html). See
  [CMMCorePlus
  documentation](https://pymmcore-plus.github.io/pymmcore-plus/api/cmmcoreplus/)
  for details.
- `CMMCorePlus` includes a `run_mda` method (name may change) "acquisition
  engine" that drives micro-manager for conventional multi-dimensional
  experiments. It accepts an
  [MDASequence](https://pymmcore-plus.github.io/useq-schema/schema/sequence/)
  from [useq-schema](https://pymmcore-plus.github.io/useq-schema/) for
  experiment design/declaration.
- Adds a [callback
  system](https://pymmcore-plus.github.io/pymmcore-plus/api/events/) that adapts
  the CMMCore callback object to an existing python event loop (such as Qt, or
  perhaps asyncio/etc...).  The `CMMCorePlus` class also fixes a number of
  "missed" events that are not currently emitted by the CMMCore API.

## Documentation

https://pymmcore-plus.github.io/pymmcore-plus/

## Why not just use `pymmcore` directly?

[pymmcore](https://github.com/micro-manager/pymmcore) is (and should probably
remain) a thin SWIG wrapper for the C++ code at the core of the
[Micro-Manager](https://github.com/micro-manager/mmCoreAndDevices/) project.  It
is sufficient to control micromanager via python, but lacks some "niceties" that
python users are accustomed to. This library:

- extends the `pymmcore.CMMCore` object with [additional
  methods](https://pymmcore-plus.github.io/pymmcore-plus/api/cmmcoreplus/)
- fixes emission of a number of events in `MMCore`.
- provide proper python interfaces for various objects like
  [`Configuration`](https://pymmcore-plus.github.io/pymmcore-plus/api/configuration/)
  and [`Metadata`](https://pymmcore-plus.github.io/pymmcore-plus/api/metadata/).
- provides an [object-oriented
  API](https://pymmcore-plus.github.io/pymmcore-plus/api/device/) for Devices
  and their properties.
- uses more interpretable `Enums` rather than `int` for [various
  constants](https://pymmcore-plus.github.io/pymmcore-plus/api/constants/)
- improves docstrings and type annotations.
- generally feel more pythonic (note however, `camelCase` method names from the
  CMMCore API are *not* substituted with `snake_case`).

## What about `Pycro-Manager`?

[Pycro-Manager](https://github.com/micro-manager/pycro-manager) is a library
designed to make it easier to work with and control the **Java** Micro-manager
application using python.  As such, it requires Java to be installed and running
in the background (either via the micro-manager GUI application directly, or via
a headless process).  The python half communicates with the Java half using
ZeroMQ messaging.

**In brief**: while `Pycro-Manager` provides a python API to control the Java
Micro-manager application (which in turn controls the C++ core), `pymmcore-plus`
provides a python API to control the C++ core directly, without the need for
Java in the loop.

## Quickstart

### Install

```sh
# from pip
pip install pymmcore-plus

# from conda
conda install -c conda-forge pymmcore-plus

# or from source tree
pip install git+https://github.com/pymmcore-plus/pymmcore-plus.git
```

Usually, you'll then want to install the device adapters (though
you can also download these manually from [micro-manager.org](https://micro-manager.org/Micro-Manager_Nightly_Builds)):

```sh
mmcore install
```

*See [installation documentation ](https://pymmcore-plus.github.io/pymmcore-plus/install/) for more details.*

### Usage

Then use the core object as you would `pymmcore.CMMCore`...
but with [more features](https://pymmcore-plus.github.io/pymmcore-plus/api/cmmcoreplus/) :smile:

```python
from pymmcore_plus import CMMCorePlus

core = CMMCorePlus()
...
```

### Examples

See a number of [usage examples in the
documentation](http://pymmcore-plus.github.io/pymmcore-plus/examples/mda/).

You can find some basic python scripts in the [examples](examples) directory of
this repository

## Contributing

Contributions are welcome!  See [contributing guide](http://pymmcore-plus.github.io/pymmcore-plus/contributing/).
