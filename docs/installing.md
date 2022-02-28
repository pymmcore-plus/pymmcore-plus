# Installing

## Installing micromanager

pymmcore-plus relies on the device adapters and C++ core provided by [mmCoreAndDevices](https://github.com/micro-manager/mmCoreAndDevices#mmcoreanddevices). For most people the easiest way to get this will be to install `micro-manager`. There are two ways to do this:

1. Download

    Go to the [micro-manager downloads](https://micro-manager.org/Micro-Manager_Nightly_Builds) page and download the latest release for your Operating System.

2. Using `install` utility.

    On Windows or Mac You can run:

    ```bash
    python -m pymmcore_plus.install
    ```

    to automatically install micro-manager.


### On Linux

On a linux based system the easiest approach is to just install the C++ core of micromanager, [mmCoreAndDevices](https://github.com/micro-manager/mmCoreAndDevices#mmcoreanddevices). To do that follow the build instructions in the `mmCoreAndDevices` README.
