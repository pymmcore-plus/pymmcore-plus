# Install

## Installing pymmcore-plus

`pymmcore-plus` can be installed with pip:

```bash
pip install pymmcore-plus
```

or with conda:

```bash
conda install -c conda-forge pymmcore-plus
```

... and then proceed to the next section to learn about device adapters.

## Installing Micro-Manager Device Adapters

Just like the underlying [`pymmcore`](https://github.com/micro-manager/pymmcore) library,
`pymmcore-plus` also relies on the device adapters and C++ core provided by
[mmCoreAndDevices](https://github.com/micro-manager/mmCoreAndDevices#mmcoreanddevices).
They can be installed in two ways:

1. **Use the `mmcore` command line tool**

    This library provides a quick way to install the latest version of micro-manager:

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
    Micro-Manager device adapters. See [below](#understanding-device-interface-versions)


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

## Understanding Device Interface Versions

Micro-Manager's C++ layer (called MMCore) controls devices via adapters that are
compiled into platform-specific shared libraries.  These libraries are always
compiled to work with a *specific* "device interface version" expected by the
MMCore object itself.  If you try to load a device adapter with a device
interface version that does not match the version expected by the core, then you
will get an error.

[pymmcore](https://github.com/micro-manager/pymmcore) is a library that wraps
the C++ code and makes it available to python.  It has a 5-number version string
that looks something like `11.1.1.71.2`.  The first three parts (here: `11.1.1`)
represent the version of the MMCore library.  The next number (here: `71`) *is
the device interface version that pymmcore expects*.  (The last number is a
pymmcore-specific build number).  To query version information of your installed
libraries you can run:

```bash
mmcore --version
```

!!! danger "Critical"

    **You *must* use device adapter libraries that were compiled for the same device
    interface version as your version of pymmcore.**

    By default, when you run `mmcore install`, it will pick the latest compatible
    version to install. However, you can also do this explicitly.  For the example
    above, for a device interface version of `71`, you could explicitly install the
    last compatible device adapters listed on the table below with `mmcore install`
    as follows:

    ```sh
    mmcore install -r 20250310
    ```

Here is a list of the latest device interface numbers, the date of the first
nightly build where they were available, the last nightly build date to support
that version, and the commit in
[mmCoreAndDevices](https://github.com/micro-manager/mmCoreAndDevices) that
bumped the version.

|Version|Release Date|Last Release|Commit|
|-------|----|-----|------|
|75|20260226|        |[3c6312ac5](https://github.com/micro-manager/mmCoreAndDevices/commit/3c6312ac5)|
|74|20250815|20260225|[7e9f2f214](https://github.com/micro-manager/mmCoreAndDevices/commit/7e9f2f214)|
|73|20250318|20250814|[55863b2d8](https://github.com/micro-manager/mmCoreAndDevices/commit/55863b2d8)|
|72|20250318|20250318|[b8de737b2](https://github.com/micro-manager/mmCoreAndDevices/commit/b8de737b2)|
|71|20221031|20250310|[7ba63fb8f](https://github.com/micro-manager/mmCoreAndDevices/commit/7ba63fb8f)|
|70|20210219|20221030|[8687ddb51](https://github.com/micro-manager/mmCoreAndDevices/commit/8687ddb51)|
|69|20180712||[1a9938168](https://github.com/micro-manager/mmCoreAndDevices/commit/1a9938168)|
|68|20171107||[285a9fbb2](https://github.com/micro-manager/mmCoreAndDevices/commit/285a9fbb2)|
|67|20160609||[2cafb3481](https://github.com/micro-manager/mmCoreAndDevices/commit/2cafb3481)|

??? information "Older versions"

    |Version|Release Date|Commit|
    |-------|----|------|
    |66|20160608|[6378720c9](https://github.com/micro-manager/mmCoreAndDevices/commit/6378720c9)|
    |65|20150528|[b98858d3b](https://github.com/micro-manager/mmCoreAndDevices/commit/b98858d3b)|
    |64|20150515|[6fdcdc274](https://github.com/micro-manager/mmCoreAndDevices/commit/6fdcdc274)|
    |63|20150505|[ae4ced454](https://github.com/micro-manager/mmCoreAndDevices/commit/ae4ced454)|
    |62|20150501|[38cfde8ef](https://github.com/micro-manager/mmCoreAndDevices/commit/38cfde8ef)|
    |61|20140801|[aac034a5c](https://github.com/micro-manager/mmCoreAndDevices/commit/aac034a5c)|
    |60|20140618|[cff69f1c2](https://github.com/micro-manager/mmCoreAndDevices/commit/cff69f1c2)|
    |59|20140515|[1a3c3c884](https://github.com/micro-manager/mmCoreAndDevices/commit/1a3c3c884)|
    |58|20140514|[b3781c0a9](https://github.com/micro-manager/mmCoreAndDevices/commit/b3781c0a9)|
    |57|20140125|[97beb0f6c](https://github.com/micro-manager/mmCoreAndDevices/commit/97beb0f6c)|
    |56|20140120|[bbf1b852c](https://github.com/micro-manager/mmCoreAndDevices/commit/bbf1b852c)|
    |55|20131221|[d9d939aed](https://github.com/micro-manager/mmCoreAndDevices/commit/d9d939aed)|
    |54|20131022|[0058a1202](https://github.com/micro-manager/mmCoreAndDevices/commit/0058a1202)|
    |53|20121108|[34329bb10](https://github.com/micro-manager/mmCoreAndDevices/commit/34329bb10)|
    |52|20120925|[feeeff5d0](https://github.com/micro-manager/mmCoreAndDevices/commit/feeeff5d0)|
    |51|20120117|[c62cd71df](https://github.com/micro-manager/mmCoreAndDevices/commit/c62cd71df)|
    |50|20120117|[121dea472](https://github.com/micro-manager/mmCoreAndDevices/commit/121dea472)|
    |49|20111026|[0f999b4f7](https://github.com/micro-manager/mmCoreAndDevices/commit/0f999b4f7)|
    |48|20111010|[5407292c4](https://github.com/micro-manager/mmCoreAndDevices/commit/5407292c4)|
    |47|20110916|[de02aa524](https://github.com/micro-manager/mmCoreAndDevices/commit/de02aa524)|
    |46|20110915|[f886a5a60](https://github.com/micro-manager/mmCoreAndDevices/commit/f886a5a60)|
    |45|20110722|[3de97a552](https://github.com/micro-manager/mmCoreAndDevices/commit/3de97a552)|
    |44|20110721|[adffbed3c](https://github.com/micro-manager/mmCoreAndDevices/commit/adffbed3c)|
    |43|20110721|[f1fa3260c](https://github.com/micro-manager/mmCoreAndDevices/commit/f1fa3260c)|
    |42|20110720|[70d420b79](https://github.com/micro-manager/mmCoreAndDevices/commit/70d420b79)|
    |41|20110626|[6f1e9e3c7](https://github.com/micro-manager/mmCoreAndDevices/commit/6f1e9e3c7)|
    |40|20110526|[c9c4f901b](https://github.com/micro-manager/mmCoreAndDevices/commit/c9c4f901b)|
    |39|20110411|[d6cf30e11](https://github.com/micro-manager/mmCoreAndDevices/commit/d6cf30e11)|
    |38|20110324|[5fb856c6d](https://github.com/micro-manager/mmCoreAndDevices/commit/5fb856c6d)|
    |39|20110322|[aca92c283](https://github.com/micro-manager/mmCoreAndDevices/commit/aca92c283)|
    |38|20101224|[3327c6083](https://github.com/micro-manager/mmCoreAndDevices/commit/3327c6083)|
    |37|20101221|[63e284ccf](https://github.com/micro-manager/mmCoreAndDevices/commit/63e284ccf)|
    |36|20100920|[7b180c4ef](https://github.com/micro-manager/mmCoreAndDevices/commit/7b180c4ef)|
    |35|20100823|[41603ae0c](https://github.com/micro-manager/mmCoreAndDevices/commit/41603ae0c)|
    |34|20100202|[5bd9a38d5](https://github.com/micro-manager/mmCoreAndDevices/commit/5bd9a38d5)|
    |28|20080911|[ecdc3ffe9](https://github.com/micro-manager/mmCoreAndDevices/commit/ecdc3ffe9)|
    |27|20080806|[644297085](https://github.com/micro-manager/mmCoreAndDevices/commit/644297085)|
    |26|20080604|[99fd3cd80](https://github.com/micro-manager/mmCoreAndDevices/commit/99fd3cd80)|
    |16|20070412|[38ebafde1](https://github.com/micro-manager/mmCoreAndDevices/commit/38ebafde1)|
    |15|20070405|[18ec4b48b](https://github.com/micro-manager/mmCoreAndDevices/commit/18ec4b48b)|
    |14|20070227|[3b69e7670](https://github.com/micro-manager/mmCoreAndDevices/commit/3b69e7670)|


    
