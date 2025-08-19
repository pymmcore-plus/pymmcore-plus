# pymmcore-plus

[![License](https://img.shields.io/pypi/l/pymmcore-plus.svg?color=green)](https://github.com/pymmcore-plus/pymmcore-plus/raw/master/LICENSE)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pymmcore-plus)](https://pypi.org/project/pymmcore-plus)
[![PyPI](https://img.shields.io/pypi/v/pymmcore-plus.svg?color=green)](https://pypi.org/project/pymmcore-plus)
[![Conda](https://img.shields.io/conda/vn/conda-forge/pymmcore-plus)](https://anaconda.org/conda-forge/pymmcore-plus)
[![CI](https://github.com/pymmcore-plus/pymmcore-plus/actions/workflows/ci.yml/badge.svg)](https://github.com/pymmcore-plus/pymmcore-plus/actions/workflows/ci.yml)
[![docs](https://github.com/pymmcore-plus/pymmcore-plus/actions/workflows/docs.yml/badge.svg)](https://pymmcore-plus.github.io/pymmcore-plus/)
[![codecov](https://codecov.io/gh/pymmcore-plus/pymmcore-plus/branch/main/graph/badge.svg)](https://codecov.io/gh/pymmcore-plus/pymmcore-plus)
[![Benchmarks](https://img.shields.io/endpoint?url=https://codspeed.io/badge.json)](https://codspeed.io/pymmcore-plus/pymmcore-plus)

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
- `pymmcore-plus` includes an [acquisition engine](https://pymmcore-plus.github.io/pymmcore-plus/guides/mda_engine/)
  that drives micro-manager for conventional multi-dimensional experiments. It accepts an
  [MDASequence](https://pymmcore-plus.github.io/useq-schema/schema/sequence/)
  from [useq-schema](https://pymmcore-plus.github.io/useq-schema/) for
  experiment design/declaration.
- Adds a [callback
  system](https://pymmcore-plus.github.io/pymmcore-plus/api/events/) that adapts
  the CMMCore callback object to an existing python event loop (such as Qt, or
  perhaps asyncio/etc...). The `CMMCorePlus` class also fixes a number of
  "missed" events that are not currently emitted by the CMMCore API.

## Documentation

<https://pymmcore-plus.github.io/pymmcore-plus/>

## Why not just use `pymmcore` directly?

[pymmcore](https://github.com/micro-manager/pymmcore) is (and should probably
remain) a thin SWIG wrapper for the C++ code at the core of the
[Micro-Manager](https://github.com/micro-manager/mmCoreAndDevices/) project. It
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
  CMMCore API are _not_ substituted with `snake_case`).

## How does this relate to `Pycro-Manager`?

[Pycro-Manager](https://github.com/micro-manager/pycro-manager) is designed to
make it easier to work with and control the Java Micro-manager application
(MMStudio) using python. As such, it requires Java to be installed and for
MMStudio to be running a server in another process. The python half communicates
with the Java half using ZeroMQ messaging.

**In brief**: while `Pycro-Manager` provides a python API to control the Java
Micro-manager application (which in turn controls the C++ core), `pymmcore-plus`
provides a python API to control the C++ core directly, without the need for
Java in the loop. Each has its own advantages and disadvantages! With
pycro-manager you retain the entire existing micro-manager ecosystem
and GUI application. With pymmcore-plus, the entire thing is python: you
don't need to install Java, and you have direct access to the memory buffers
used by the C++ core.  Work on recreating the gui application in python
being done in [`pymmcore-widgets`](https://github.com/pymmcore-plus/pymmcore-widgets)
and [`pymmcore-gui`](https://github.com/pymmcore-plus/pymmcore-gui).

## Quickstart

### Install

from pip

```sh
pip install pymmcore-plus

# or, add the [cli] extra if you wish to use the `mmcore` command line tool:
pip install "pymmcore-plus[cli]"

# add the [io] extra if you wish to use the tiff or zarr writers
pip install "pymmcore-plus[io]"
```

from conda

```sh
conda install -c conda-forge pymmcore-plus
```

dev version from github

```sh
pip install 'pymmcore-plus[cli] @ git+https://github.com/pymmcore-plus/pymmcore-plus'
```

Usually, you'll then want to install the device adapters. Assuming you've
installed with `pip install "pymmcore-plus[cli]"`, you can run:

```sh
mmcore install
```

(you can also download these manually from [micro-manager.org](https://micro-manager.org/Micro-Manager_Nightly_Builds))

_See [installation documentation](https://pymmcore-plus.github.io/pymmcore-plus/install/) for more details._

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

Contributions are welcome! See [contributing guide](http://pymmcore-plus.github.io/pymmcore-plus/contributing/).
