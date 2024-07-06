# Install

## Installing pymmcore-plus

`pymmcore-plus` can be installed with pip:

```bash
pip install pymmcore-plus

# or, add the [cli] extra if you wish to use the `mmcore` command line tool:

pip install "pymmcore-plus[cli]"
```

or with conda:

```bash
conda install -c conda-forge pymmcore-plus
```

## Installing Micro-Manager Device Adapters

Just like the underlying [`pymmcore`](https://github.com/micro-manager/pymmcore) library,
`pymmcore-plus` also relies on the device adapters and C++ core provided by
[mmCoreAndDevices](https://github.com/micro-manager/mmCoreAndDevices#mmcoreanddevices).
They can be installed in two ways:

1. **Use the `mmcore` command line tool**

    If you've installed with `pip install "pymmcore-plus[cli]"`, this library provides
    a quick way to install the latest version of micro-manager:

    ```bash
    mmcore install
    ```

    This will download the latest release of micro-manager and, by default, place it in
    a `pymmcore-plus\mm` folder in the user's data directory (e.g. `C:\Users\UserName\AppData\Local\pymmcore-plus\mm`). If you would like to modify
    the location of the installation, or the release of micro-manager to install, you can use
    the `--dest` and `--release` flags respectively.

    For more information on the `install` command, run:

    ```bash
    mmcore install --help
    ```

    To explore all the `mmcore` command line tool functionalities, run:

    ```bash
    mmcore --help
    ```

2. **Download manually from micro-manager.org**

    Go to the [micro-manager
    downloads](https://micro-manager.org/Micro-Manager_Nightly_Builds) page and
    download the latest release for your Operating System.

!!! danger "Critical"

    The *device interface version* MUST match between `pymmcore` and the
    Micro-Manager device adapters.

    The device interface version of a given `pymmcore` version is the
    fourth part in the version number (e.g. v11.1.1.**71**.0), and can also be
    identified with the following command:

    ```bash
    mmcore --version
    ```

    or, if you didn't install with the `cli` extra:

    ```bash
    python -c "print(__import__('pymmcore').CMMCore().getAPIVersionInfo())"
    ```

    The device interface version of a given Micro-Manager installation can be viewed
    in **Help > About Micro-Manager**.  Or you can look at the `MMDevice.h` file for
    the corresponding date, roughly
    [here](https://github.com/micro-manager/mmCoreAndDevices/blob/main/MMDevice/MMDevice.h#L30)

## Show the currently used Micro-Manager installation

To see which micro-manager installation `pymmcore-plus` is using, you
can run:

```shell
mmcore list
```

or, if you didn't install with the `cli` extra, you can use
[`find_micromanager`][pymmcore_plus.find_micromanager]:

```shell
python -c "from pymmcore_plus import find_micromanager; print(find_micromanager())"
```

## Set the active Micro-Manager installation

By default, `pymmcore-plus` will look for a `Micro-Manager` folder in the
default install location. On Windows this is `C:\Program Files\`, on macOS it is
`/Applications/` and on Linux it is `/usr/local/lib/`. To override these default
device adapter search path, set the `MICROMANAGER_PATH` environment variable

```shell
export MICROMANAGER_PATH=/path/to/installation
```

If you want to permanently set the Micro-Manager installation path that
`pymmcore-plus` uses, you can use the `mmcore use` command:

```shell
mmcore use <some path or pattern>
```

... where `<some path or pattern>` is either a path to an existing directory
(containing micro-manager device adapters) or a pattern to match against
directories returned by [`find_micromanager`][pymmcore_plus.find_micromanager].

Alternatively, you can use the
[`use_micromanager`][pymmcore_plus.use_micromanager] function, passing *either*
a path to an existing directory, or a pattern to match against directories
returned by [`find_micromanager`][pymmcore_plus.find_micromanager]:

```shell
python -c "from pymmcore_plus import use_micromanager; use_micromanager(path=..., pattern=...)"
```

### On Linux

On a linux based system the easiest approach is to just install the C++ core of
micromanager,
[mmCoreAndDevices](https://github.com/micro-manager/mmCoreAndDevices#mmcoreanddevices).
To do that follow the [build
instructions](https://github.com/micro-manager/micro-manager/blob/main/doc/how-to-build.md#building-on-unix)
in the micro-manager repo.
