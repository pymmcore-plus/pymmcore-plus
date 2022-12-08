# Install

## Installing pymmcore-plus

`pymmcore-plus` can be installed with pip:

```bash
pip install pymmcore-plus
```

... as well as conda:

```bash
conda install -c conda-forge pymmcore-plus
```

## Installing Micro-Manager Device Adapters

Just like underlying the [`pymmcore`](https://github.com/micro-manager/pymmcore)
that this library, `pymmcore-plus` relies on the device adapters and C++ core
provided by
[mmCoreAndDevices](https://github.com/micro-manager/mmCoreAndDevices#mmcoreanddevices).
There are two ways to do this:

1. **Use the `pymmcore_plus.install` module**

    This library provides a quick way to install the latest version of
    micro-manager:

    ```bash
    mmcore install
    ```

    This will download the latest release of micro-manager and place it in the
    pymmcore-plus folder.  If you would like to modify the location of the
    installation, or the release of micro-manager to install, you can use the
    `--dest` and `--release` flags respectively.

    For more information, run:

    ```bash
    mmcore install --help
    ```

2. **Download manually from micro-manager.org**

    Go to the [micro-manager
    downloads](https://micro-manager.org/Micro-Manager_Nightly_Builds) page and
    download the latest release for your Operating System.

!!! danger "Critical"

    The *device interface version* MUST match between pymmcore and the
    Micro-Manager device adapters.

    The device interface version of a given pymmcore version is the
    fourth part in the version number, and can also be with the following
    command:

    ```bash
    python -c "print(__import__('pymmcore').CMMCore().getAPIVersionInfo())"
    ```

    The device interface version of a given Micro-Manager installation can be viewed
    in **Help > About Micro-Manager**.  Or you can look at the `MMDevice.h` file for
    the corresponding date, roughly
    [here](https://github.com/micro-manager/mmCoreAndDevices/blob/main/MMDevice/MMDevice.h#L30)

!!! tip

    By default, `pymmcore-plus` will look for a `Micro-Manager` folder in the
    default install location. On Windows this is `C:\Program Files\`, on macOS it is
    `/Applications/` and on Linux it is `/usr/local/lib/`. To override these default
    device adapter search path, set the `MICROMANAGER_PATH` environment variable.

    To see which micro-manager installation `pymmcore-plus` is using, you
    can run:

    ```shell
    python -c "from pymmcore_plus import find_micromanager; print(find_micromanager())"
    ```


### On Linux

On a linux based system the easiest approach is to just install the C++ core of
micromanager,
[mmCoreAndDevices](https://github.com/micro-manager/mmCoreAndDevices#mmcoreanddevices).
To do that follow the build instructions in the `mmCoreAndDevices` README.
