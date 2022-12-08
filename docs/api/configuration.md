# Configuration & Groups

Configuring a microscope with micro-manager entails storing and retrieving
a number of device parameters settings.  In general, a single setting comprises
a device name, a property name, and a value.  A **Configuration** object
represents a *collection* of individual settings; that is, it represents a number
of device parameters all in a specific state, such as would be used to prepare
the microscope to image a specific channel, like "DAPI", or "FITC".

A **Configuration Group** is, in turn, a *collection* of `Configuration` objects;
for example, all of the `Configuration` objects that represent different
"Channel" settings.

Conceptually, Configurations and Groups are organized like this:

```YAML
ConfigGroupA:
    Configuration1:
        deviceA:
            propertyA: 'value_a'
            propertyB: 'value_b'
        deviceB:
            propertyC: 'value_c'
        ...
    Configuration2:
        deviceA:
            propertyA: 'value_d'
            propertyB: 'value_e'
        deviceB:
            propertyC: 'value_f'
        ...
    ...
ConfigGroupB:
    Configuration1:
        deviceC:
            propertyA: 'value_g'
        ...
    ...
```

## `pymmcore-plus` Objects

MMCore and pymmcore's
[configuration](https://valelab4.ucsf.edu/~MM/doc/MMCore/html/class_configuration.html)
object implements a basic mutable mapping interface, but with custom method
names like `addSetting`, `getSetting`, and `deleteSetting` methods).

`pymmcore-plus` provides a [`Configuration`][pymmcore_plus.Configuration]
subclass that implements a [`MutableMapping`][collections.abc.MutableMapping] interface,
allowing dict-like access to the configuration, where the keys are 2-tuples of
`(deviceLabel, propertyLabel)` and the values are the property values. (Note,
however, that iterating of a `Configuration` object behaves like iterating over
a list of 3-tuples `(deviceLabel, propertyLabel, value)`, not a dict.)

`pymmcore-plus` also offers a [`ConfigGroup`][pymmcore_plus.ConfigGroup] object,
which is a [`MutableMapping`][collections.abc.MutableMapping] where the keys are
[Configuration
Preset](https://micro-manager.org/Micro-Manager_Configuration_Guide#configuration-presets)
names and the values are `Configuration` objects.

::: pymmcore_plus.Configuration
    options:
        heading_level: 3

::: pymmcore_plus.ConfigGroup
    options:
        heading_level: 3
