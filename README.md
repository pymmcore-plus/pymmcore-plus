# pymmcore-plus

[![License](https://img.shields.io/pypi/l/pymmcore-plus.svg?color=green)](https://github.com/tlambert03/pymmcore-plus/raw/master/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/pymmcore-plus.svg?color=green)](https://pypi.org/project/pymmcore-plus)
[![Python Version](https://img.shields.io/pypi/pyversions/pymmcore-plus.svg?color=green)](https://python.org)
[![CI](https://github.com/tlambert03/pymmcore-plus/actions/workflows/test_and_deploy.yml/badge.svg)](https://github.com/tlambert03/pymmcore-plus/actions/workflows/test_and_deploy.yml)
[![codecov](https://codecov.io/gh/tlambert03/pymmcore-plus/branch/main/graph/badge.svg)](https://codecov.io/gh/tlambert03/pymmcore-plus)

#### 🧪🧪 pre-alpha software: work in progress!  🧪🧪

`pymmcore-plus` aims to extend [pymmcore](https://github.com/micro-manager/pymmcore) (python bindings for the C++ [micro-manager core](https://github.com/micro-manager/mmCoreAndDevices/)) with a number of features designed to facilitate working with **Micro-manager in pure python/C environments**.

- `pymmcore_plus.CMMCorePlus` is a subclass of `pymmcore.CMMCore` that provides additional convenience functions beyond the standard [CMMCore API](https://javadoc.scijava.org/Micro-Manager-Core/mmcorej/CMMCore.html).

  ```py
  from pymmcore_plus import CMMCorePlus
  ```
- `CMMCorePlus` includes a `run_mda` method (name may change) "acquisition engine" that drives micro-manager for conventional multi-dimensional experiments. It accepts an [MDASequence](https://github.com/tlambert03/useq-schema#mdasequence) from [useq-schema](https://github.com/tlambert03/useq-schema) for experiment design/declaration.
- Adds a callback system that adapts the CMMCore callback object to an existing python event loop (such as Qt, or perhaps asyncio/etc...)
- Includes a [Pyro5](https://pyro5.readthedocs.io/en/latest/)-based client/server that allows one to create and control and CMMCorePlus instance running in another process, or (conceivably) another computer.  This is particularly useful for integration in an existing event loop (without choking the main python thread).

  ```py
  from pymmcore_plus import RemoteMMCore

  with RemoteMMCore() as mmcore:
      mmcore.loadSystemConfiguration("demo")
      print(mmcore.getLoadedDevices())
  ```

## Why does this exist?

[pymmcore](https://github.com/micro-manager/pymmcore) is (and should probably
remain) a pure SWIG wrapper for the C++ code at the core of the
[Micro-Manager](https://github.com/micro-manager/mmCoreAndDevices/) project.  It
is sufficient to control micromanager via python, but lacks some "niceties" that
python users are accustomed to.  This library can extend the core object, add
additional methods, docstrings, type hints, etc... and generally feel more
pythonic (note however, `camelCase` method names from the CMMCore API are *not*
converted to `snake_case`.)

[pycro-manager](https://github.com/micro-manager/pycro-manager) is an excellent
library designed to make it easier to work with and control Micro-manager using
python.  It's [core acquisition
engine](https://github.com/micro-manager/AcqEngJ), however, is written in Java, requiring java to be installed and running in the background (either via
the micro-manager GUI application directly, or via a headless process).  The
python half communicates with the Java half using ZeroMQ messaging.

Among other things, this package aims to provide a pure python / C++
implementation of a MMCore acquisition engine, with no Java dependency (see
`CMMCorePlus.run_mda`... it's minimal at the moment and lacks acquisition
hooks). To circumvent issues with the GIL, this library also provides a
`pymmcore_plus.RemoteMMCore` proxy object (via
[Pyro5](https://github.com/irmen/Pyro5)) that provides a server/client interface
for inter-process communication (this serves the same role as the ZMQ server in
pycro-manager... but in this case it's communicating with another python process
instead of a Java process).

> side-note: the `useq.MDASequence` object that this library uses to define
> experiments can also generate events [consumable by
> pycro-manager](https://github.com/tlambert03/useq-schema#example-mdasequence-usage).
> So if you prefer the `pycro-manager` approach, but also like the `MDASequence`
> schema, you can use both.

Finally, the `CMMCorePlus` class here adds a callback mechanism that makes it
easier to adapt the native MMCore callback system to multiple listeners, across
multiple process, which makes it easier to incorporate `pymmcore-plus` into
existing event loops (like a [Qt event loop](examples/qt_integration.py)).  See
[`napari-micromanager`](https://github.com/tlambert03/napari-micromanager) for a
nascent project that adds Qt-based GUI interface on top of an interprocess
`RemoteMMCore`.

## Quickstart

### install

```sh

# from pip
pip install pymmcore-plus

# or from source
git clone https://github.com/tlambert03/pymmcore-plus.git
cd pymmcore-plus
pip install -e .
```

#### device adapters

In most cases you will want the Micro-manager device adapter libraries.  These
can be downloaded and installed the usual way from the [Micro-manager
website](https://micro-manager.org/wiki/Micro-Manager_Nightly_Builds) (use
version 2.0-gamma), or, you can use the included installation script to install
to the pymmcore-plus install folder:

```sh
python -m pymmcore_plus.install
```

> By default, `pymmcore-plus` will look first for the Micro-Manager device
> adapters installed using the above command (i.e. in the current or
> `pymmcore_plus` folders), and will then look in your Applications or Program
> Files directory.  To override these default device adapter search path, set the
> `MICROMANAGER_PATH` environment variable.

**Important:** The *device interface version* must match between pymmcore and the Micro-Manager device adapters.

The device interface version of a given `pymmcore` version is the fourth part in the version number, and can also be with the following command:

```sh
python -c "print(__import__('pymmcore').CMMCore().getAPIVersionInfo())"
```

The device interface version of a given Micro-Manager installation can be viewed in **Help > About Micro-Manager**.  Or you can look at the `MMDevice.h` file for the corresponding date, roughly [here](https://github.com/micro-manager/mmCoreAndDevices/blob/main/MMDevice/MMDevice.h#L30)

## Examples

You can find for some basic examples in the [examples](examples) directory.

#### run a basic MDASequence from [`useq-schema`](https://github.com/tlambert03/useq-schema)

create `MMCore` in the main thread.

```sh
python examples/run_mda.py
```

```python
from pymmcore_plus import CMMCorePlus
from useq import MDASequence

# see
sequence = MDASequence(
    channels=["DAPI", {"config": "FITC", "exposure": 50}],
    time_plan={"interval": 2, "loops": 5},
    z_plan={"range": 4, "step": 0.5},
    axis_order="tpcz",
)

mmc = CMMCorePlus()
# this will load the `MMConfig_demo.cfg` in your micromanager path
mmc.loadSystemConfiguration("demo")
mmc.run_mda(sequence)
```

#### attach to or start a remote CMMCorePlus server


```sh
python examples/basic_client.py
```

```python
from pymmcore_plus import RemoteMMCore

with RemoteMMCore() as mmcore:
    mmcore.loadSystemConfiguration("demo")
    print("loaded:", mmcore.getLoadedDevices())
    ...
```

#### use with an event loop

see [`qt_integration`](examples/qt_integration.py) for a slightly more 'realistic'
example that drives an experiment in another process using a `RemoteMMCore` proxy,
while receiving feedback in a Qt event loop in the main python thread.

```sh
python examples/qt_integration.py
```

> note: you'll need to `pip install qtpy pyqt5` (or `pyside2`) for this to work


## Contributing

Contributions welcome.  Please fork this library, then clone locally, then install with extras
```
pip install -e .[testing]
```
Run `pre-commit install` to add pre-commit hooks (black, flake8, mypy, etc...)
Run tests with `pytest`
