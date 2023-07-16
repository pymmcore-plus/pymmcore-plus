"""pythonic wrapper on pymmcore.Configuration object."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Iterator, Tuple, overload

import pymmcore
from typing_extensions import TypeAlias

DevPropValueTuple: TypeAlias = Tuple[str, str, str]
DevPropTuple: TypeAlias = Tuple[str, str]


class Configuration(pymmcore.Configuration):
    """Encapsulation of configuration information.

    This is the type of object returned by default (provided `native==False`) by:
    [`getConfigData][pymmcore_plus.CMMCorePlus.getConfigData],
    [`getPixelSizeConfigData][pymmcore_plus.CMMCorePlus.getPixelSizeConfigData]
    [`getSystemState][pymmcore_plus.CMMCorePlus.getSystemState]
    [`getSystemStateCache][pymmcore_plus.CMMCorePlus.getSystemStateCache]
    [`getConfigState][pymmcore_plus.CMMCorePlus.getConfigState]
    [`getConfigGroupState][pymmcore_plus.CMMCorePlus.getConfigGroupState]
    [`getConfigGroupStateFromCache][pymmcore_plus.CMMCorePlus.getConfigGroupStateFromCache]


    This class is a subclass of `pymmcore.Configuration` that implements an
    [`collections.abc.MutableSequence`][] (i.e. it behaves like a Python list).
    It also behaves much like a [`collections.abc.MutableMapping`][], where the keys
    are 2-tuples of (deviceLabel, propertyLabel) and the values are the property values.

    Note that the "order" of this collection is not well-defined, so while you *can*
    index with an integer, you should not rely on the order of the items in the
    collection.  `__getitem__/__setitem__/__delitem__` all accept a 2-tuple of
    `(deviceLabel, propertyLabel)`.

    It adds a few convenience methods:

    !!! tip

        All of the methods in `pymmcore_plus.CMMCorePlus` that would have returned a
        `pymmcore.Configuration` in `pymmcore` (e.g.
        [`getConfigData`][pymmcore_plus.CMMCorePlus.getConfigData],
        [`getConfigState`][pymmcore_plus.CMMCorePlus.getConfigState], etc...).
        have been reimplemented to return a `pymmcore_plus.Configuration` object. This
        object has the same API as `pymmcore.Configuration`, but you can request a
        "native" (unenhanced) `pymmcore` object by passing `native=True` to the method.
    """

    # pymmcore API:
    # def __init__(self) -> None: ...
    # def addSetting(self, setting: PropertySetting) -> None: ...
    # def deleteSetting(self, device: str, prop, str) -> None: ...
    # @overload
    # def getSetting(self, index: int) -> PropertySetting: ...
    # @overload
    # def getSetting(self, device: str, prop: str) -> PropertySetting: ...
    # def getVerbose(self) -> str: ...
    # def isConfigurationIncluded(self, cfg: Configuration) -> bool: ...
    # def isPropertyIncluded(self, device: str, prop: str) -> bool: ...
    # def isSettingIncluded(self, ps: PropertySetting) -> bool: ...
    # def size(self) -> int: ...

    def __len__(self) -> int:
        return self.size()

    @overload
    def __getitem__(self, key: int) -> pymmcore.PropertySetting:
        ...

    @overload
    def __getitem__(self, key: DevPropTuple) -> str:
        ...

    def __getitem__(self, key: int | DevPropTuple) -> str | pymmcore.PropertySetting:
        """Get property setting by index or (devLabel, propLabel) key.

        If `key` is an integer, returns the `pymmcore.PropertySetting` at that index.
        If `key` is a 2-tuple of strings, returns the value of the property setting
        with that (devLabel, propLabel) key.
        """
        if isinstance(key, int):
            return self.getSetting(key)
        if isinstance(key, tuple) and len(key) == 2:
            return self.getSetting(*key).getPropertyValue()
        raise TypeError("key must be either an int or 2-tuple of strings.")

    def __setitem__(self, key: DevPropTuple, value: str) -> None:
        """Set property setting by `(devLabel, propLabel)` key."""
        if not isinstance(key, tuple) or len(key) != 2:
            raise TypeError("key must be a 2-tuple of strings.")
        # note: pymmcore will automatically overwrite property settings with the same
        # (devLabel, propLabel) key
        self.addSetting(pymmcore.PropertySetting(*key, value))

    def __delitem__(self, key: DevPropTuple) -> None:
        """Delete setting for `(devLabel, propLabel)` from the configuration."""
        if not isinstance(key, tuple) or len(key) != 2:
            raise TypeError("key must be a 2-tuple of strings.")
        self.deleteSetting(*key)  # type: ignore  # error in stub.

    def remove(self, key: DevPropTuple) -> None:
        """Remove setting for `(devLabel, propLabel)` from the configuration."""
        if not self.isPropertyIncluded(*key):
            raise ValueError(f"No setting for key {key!r}")
        del self[key]

    def append(self, setting: pymmcore.PropertySetting | DevPropValueTuple) -> None:
        """Add a setting to the configuration."""
        if isinstance(setting, tuple):
            if len(setting) != 3:
                raise ValueError("value must be a 3-tuple of (device, property, value)")
            setting = pymmcore.PropertySetting(*setting)
        self.addSetting(setting)

    def extend(
        self,
        other: pymmcore.Configuration
        | Iterable[pymmcore.PropertySetting | DevPropValueTuple],
    ) -> None:
        """Add all settings from another Configuration."""
        if isinstance(other, pymmcore.Configuration):
            for i in range(other.size()):
                self.addSetting(other.getSetting(i))
        else:
            for setting in other:
                self.append(setting)

    def __iter__(self) -> Iterator[DevPropValueTuple]:
        for i in range(self.size()):
            ps = self.getSetting(i)
            yield ps.getDeviceLabel(), ps.getPropertyName(), ps.getPropertyValue()

    def __contains__(
        self,
        query: pymmcore.Configuration
        | pymmcore.PropertySetting
        | DevPropTuple
        | DevPropValueTuple,
    ) -> bool:
        if isinstance(query, pymmcore.Configuration):
            return self.isConfigurationIncluded(query)
        if isinstance(query, pymmcore.PropertySetting):
            return self.isSettingIncluded(query)
        if isinstance(query, tuple):
            if len(query) == 2:
                return self.isPropertyIncluded(*query)
            if len(query) == 3:
                return self.isSettingIncluded(pymmcore.PropertySetting(*query))
        raise TypeError(
            "Configuration.__contains__ expects a Configuration, a PropertySetting,"
            " a 2-tuple (deviceLabel, propertyLabel) or a 3-tuple ",
            "(deviceLabel, propertyLabel, value).",
        )

    def __repr__(self) -> str:
        return f"<MMCorePlus Configuration with {self.size()} settings>"

    def __str__(self) -> str:
        lines = []
        for device, prop in self.dict().items():
            lines.append(f"{device}:")
            lines.extend(f"  - {name}: {value}" for name, value in prop.items())
        return "\n".join(lines)

    def html(self) -> str:
        """Return config representation as HTML."""
        return self.getVerbose()

    def dict(self) -> dict[str, dict[str, str]]:
        """Return config as a nested dict {Device: {Property: Value}}."""
        d: defaultdict[str, dict[str, str]] = defaultdict(dict)
        for label, prop, value in self:
            d[label][prop] = value
        return dict(d)

    @classmethod
    def from_configuration(cls, config: pymmcore.Configuration) -> Configuration:
        """Create Configuration (Plus) from pymmcore.Configuration."""
        new = cls()
        for s in range(config.size()):
            new.addSetting(config.getSetting(s))
        return new

    @classmethod
    def create(cls, *args: Any, **kwargs: Any) -> Configuration:
        """More flexible init to create a `Configuration`.

        Can create from:
        1. A dict of dicts (outer key is device, inner key is prop)
        2. A sequence of 3-tuple
        3. kwargs: where the key is the device, and the value is a {prop: value} map
        """
        cfg = cls()
        if args:
            if len(args) > 1:  # pragma: no cover
                raise ValueError(
                    f"create takes 1 positional argument but {len(args)} were given"
                )

            arg = args[0]
            err_msg = "Argument must be either a dict of dicts, or a list of 3-tuple"

            if isinstance(arg, dict):
                kwargs = {**arg, **kwargs}
            elif isinstance(arg, (tuple, list)):
                for item in arg:
                    if len(item) != 3:
                        raise ValueError(err_msg)
                    cfg.addSetting(pymmcore.PropertySetting(*(str(x) for x in item)))
            else:
                raise ValueError()
        if kwargs:
            for dev_label, props in kwargs.items():
                if not isinstance(props, dict):
                    raise ValueError(err_msg)
                for prop, value in props.items():
                    cfg.addSetting(
                        pymmcore.PropertySetting(dev_label, prop, str(value))
                    )
        return cfg

    def __eq__(self, o: Any) -> bool:
        return o.dict() == self.dict() if isinstance(o, Configuration) else False


# class PropertySetting(pymmcore.PropertySetting):
#     """Encompasses a device label, property name, and property value"""

#     # pymmcore API:
#     # def getDeviceLabel(self) -> str:  # i.e. 'Camera'
#     # def getKey(self) -> str:  # ie. 'Camera-Binning'
#     # def getPropertyName(self) -> str:  # ie. 'Binning'
#     # def getPropertyValue(self) -> str:  # ie. '1'
#     # def getReadOnly(self) -> bool:
#     # def getVerbose(self) -> str:  # ie. 'Camera:Binning=1'
#     # def isEqualTo(self, ps: PropertySetting) -> bool:# devLabel, propName & value eq

#     @classmethod
#     def from_property_setting(cls, ps: pymmcore.PropertySetting) -> PropertySetting:
#         label = ps.getDeviceLabel()
#         prop = ps.getPropertyName()
#         value = ps.getPropertyValue()
#         readOnly = ps.getReadOnly()
#         return cls(label, prop, value, readOnly)

#     def __repr__(self) -> str:
#         return f"<PropertySetting '{self}'>"

#     def __str__(self) -> str:
#         return self.getVerbose().replace(":=", "")

#     def __iter__(self) -> Iterable[str]:
#         yield self.getDeviceLabel()
#         yield self.getPropertyName()
#         yield self.getPropertyValue()
