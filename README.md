# pymmcore-plus

#### 🧪🧪 pre-alpha software: work in progress!  🧪🧪

`pymmcore-plus` aims to extend [pymmcore](https://github.com/micro-manager/pymmcore) (python bindings for the C++ [micro-manager core](https://github.com/micro-manager/mmCoreAndDevices/)) with a number of features:

- `pymmcore_plus.CMMCorePlus` is a subclass of `pymmcore.CMMCore` that provides additional convenience functions beyond the standard [CMMCore API](https://javadoc.scijava.org/Micro-Manager-Core/mmcorej/CMMCore.html).
- `CMMCorePlus` includes a `run_mda` (name may change) "acquisition engine" drives micro-manager for conventional multi-dimensional experiments. This uses the [MDASequence](https://github.com/tlambert03/useq-schema#mdasequence) from [useq-schema](https://github.com/tlambert03/useq-schema) for experiment design/declaration.
- Includes a [Pyro5](https://pyro5.readthedocs.io/en/latest/)-based client/server that allows one to create and control and CMMCorePlus instance running in another process, or (conceivably) another computer.  This is particularly useful for integration in an existing event loop (without choking the main python thread).

  ```py
  from pymmcore_plus import RemoteMMCore

  with RemoteMMCore() as mmcore:
      mmcore.loadSystemConfiguration("demo")
      print(mmcore.getLoadedDevices())
  ```

## Why does this package exist?

[pymmcore](https://github.com/micro-manager/pymmcore) is (and should probably
remain) a pure SWIG wrapper for the C++ code at the core of the
[Micro-Manager](https://github.com/micro-manager/mmCoreAndDevices/) project.  It
is sufficient to control micromanager via python, but lacks some "niceties" that
python users are accustomed to.  This library can extend the core object, add
additional methods, docstrings, type hints, etc... and general feel more
pythonic (note however, `camelCase` method names from the CMMCore API are *not*
converted to `snake_case`.)

[pycro-manager](https://github.com/micro-manager/pycro-manager) is an excellent
library designed to make it easier to work with and control Micro-manager using
python.  It's [core acquisition
engine](https://github.com/micro-manager/AcqEngJ), however, is written in Java,
thus requiring java to be installed and running in the background (either via
the micro-manager GUI application directly, or via a headless process).  The
python half communicates with the Java half using ZeroMQ messaging.

Among other things this package aims to provide a pure python & C++
implementation of an MMCore acquisition engine.  (It's very minimal at the
moment, and lacks hooks ... but see `CMMCorePlus.run_mda`). To circumvent issues
with the GIL, this library also provides a `pymmcore_plus.RemoteMMCore` proxy
object (via [Pyro5](https://github.com/irmen/Pyro5)) that provides a
server/client interface for inter-process communication (this serves the same
role as the ZMQ server in pycro-manager... but in this case it's communicating
with another python process instead of a Java process).

> side-note: the useq.MDASequence object that this library uses to define
> experiments can also generate events [consumable by
> pycro-manager](https://github.com/tlambert03/useq-schema#example-mdasequence-usage)

## quickstart

### install

```sh
# not yet available
# pip install pymmcore-plus

git clone https://github.com/tlambert03/pymmcore-plus.git
cd pymmcore-plus
pip install -e .
```

### get device adapters

In most cases you will need/want device adapters.  These can be downloaded and
installed the usual way from the [Micro-manager
website](https://micro-manager.org/wiki/Micro-Manager_Nightly_Builds) (use
version 2.0-gamma), or, you can use the included installation script to install
to the pymmcore-plus install folder:

```sh
python -m pymmcore_plus.install
```

> Tip: By default, pymmcore-plus will look first for the `Micro-Manager` device
> adapters installed using the above command (i.e. in the pymmcore-plus folder),
> and will then look in your Applications or Program Files directory.  To
> override the default device adapter search path, set the `MICROMANAGER_PATH`
> environment variable.

### examples

Look for some basic examples in the [examples](examples) directory.

#### run a basic MDASequence from [`useq-schema`](https://github.com/tlambert03/useq-schema)

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

```python
from pymmcore_plus import RemoteMMCore

with RemoteMMCore() as mmcore:
    mmcore.loadSystemConfiguration("demo")
    print("loaded:", mmcore.getLoadedDevices())
    ...
```
