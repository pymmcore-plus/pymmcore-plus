# Device & Property objects

`pymmcore-plus` offers two classes that provide a more **object-oriented** interface
to common operations and queries performed on devices and their properties.

In the original `CMMCore` API, there are a lot of methods that accept a
`deviceLabel` string as the first argument (and perhaps additional arguments)
and query something about that device (e.g.
[`getDeviceLibrary`][pymmcore.CMMCore.getDeviceLibrary],
[`getDeviceType`][pymmcore_plus.CMMCorePlus.getDeviceType],
[`waitForDevice`][pymmcore.CMMCore.waitForDevice], etc...).  In `pymmcore-plus`, the
[`Device`][pymmcore_plus.Device] class acts as a "view" onto a specific device, and
these methods are implemented as methods (that no longer require the `deviceLabel` argument),
and the `deviceLabel` is passed to the constructor.

Similarly, there are many methods in the `CMMCore` API that require both a
device label and a device property name, and modify that specific property (e.g.
[`isPropertySequenceable`][pymmcore.CMMCore.isPropertySequenceable],
[`getProperty`][pymmcore.CMMCore.getProperty],
[`isPropertyReadOnly`][pymmcore.CMMCore.isPropertyReadOnly], etc...).  Here, the
[`DeviceProperty`][pymmcore_plus.DeviceProperty] class acts as a "view" onto a specific
device property, with an object-oriented interface to these methods.

::: pymmcore_plus.DeviceAdapter
    options:
        show_source: true

::: pymmcore_plus.Device
    options:
        show_source: true

::: pymmcore_plus.DeviceProperty
    options:
        show_source: true

::: pymmcore_plus.core._property.InfoDict
