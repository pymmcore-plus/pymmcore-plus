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

## Installing micro-manager

Just like underlying the [`pymmcore`](https://github.com/micro-manager/pymmcore)
that this library, `pymmcore-plus` relies on the device adapters and C++ core
provided by
[mmCoreAndDevices](https://github.com/micro-manager/mmCoreAndDevices#mmcoreanddevices).
There are two ways to do this:

1. **Use the `pymmcore_plus.install` module**

    This library provides a quick way to install the latest version of
    micro-manager:

    ```bash
    python -m pymmcore_plus.install
    ```

    This will download the latest release of micro-manager and place it in the
    pymmcore-plus folder.  If you would like to modify the location of the
    installation, or the version of micro-manager to install, you can use the
    `--dest` and `--version` flags respectively.

    For more information, run:

    ```bash
    python -m pymmcore_plus.install --help
    ```

2. **Download manually from micro-manager.org**

    Go to the [micro-manager
    downloads](https://micro-manager.org/Micro-Manager_Nightly_Builds) page and
    download the latest release for your Operating System. `pymmcore-plus` will
    look for a `Micro-Manager` folder in the default install location. On
    Windows this is `C:\Program Files\`, on macOS it is `/Applications/` and on
    Linux it is `/usr/local/lib/`.

!!! tip
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
