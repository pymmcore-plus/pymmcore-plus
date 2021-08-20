"""pythonic wrapper on pymmcore.Configuration object."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, DefaultDict, Dict, Iterator, Tuple

import pymmcore

_NULL = object()


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


class Configuration(pymmcore.Configuration):
    """Encapsulation of the configuration information, with convenience methods.

    This pymmcore_plus variant provides additional conveniences:
        __len__ - number of settings
        __str__ - pretty printing of Config
        __contains__ - check if (devLabel, propLabel) is in the config
        __getitem__ - get property setting by index or (devLabel, propLabel) key
        __iter__ - iterate over (devLabeL, propLabel, value) tuples
        dict() - convert Configuration to nested dict
        json() - convert to JSON string
        yaml() - convert to YAML string (requires PyYAML)
        html() - convert to HTML string
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

    def __repr__(self) -> str:
        return f"<MMCore Configuration with {self.size()} settings>"

    def __str__(self) -> str:
        lines = []
        for device, prop in self.dict().items():
            lines.append(f"{device}:")
            for name, value in prop.items():
                lines.append(f"  {name}={value}")
            lines.append("")
        return "\n".join(lines)

    def __iter__(self) -> Iterator[Tuple[str, str, str]]:
        for i in range(self.size()):
            ps = self.getSetting(i)
            yield ps.getDeviceLabel(), ps.getPropertyName(), ps.getPropertyValue()

    def __getitem__(self, key):
        """get property setting by index or (devLabel, propLabel) key"""
        if isinstance(key, int):
            return self.getSetting(key).getPropertyValue()
        if isinstance(key, tuple):
            return self.getSetting(*key).getPropertyValue()
        raise TypeError("key must be either an int or 2-tuple of strings.")

    def __contains__(self, query):
        if isinstance(query, pymmcore.Configuration):
            return self.isConfigurationIncluded(query)
        if isinstance(query, pymmcore.PropertySetting):
            return self.isSettingIncluded(query)
        if (
            not isinstance(query, (list, tuple))
            or len(query) != 2
            or not all(isinstance(i, str) for i in query)
        ):
            raise TypeError(
                "Configuration.__contains__ expects a Configuration, a PropertySetting,"
                " or a 2-tuple of (deviceLabel, propertyLabel)"
            )
        return self.isPropertyIncluded(*query)

    def html(self) -> str:
        """Return config as HTML."""
        return self.getVerbose()

    def dict(self) -> Dict[str, Dict[str, str]]:
        """Return config as a nested dict"""
        d: DefaultDict[str, Dict[str, str]] = defaultdict(dict)
        for label, prop, value in self:
            d[label][prop] = value
        return dict(d)

    def json(self) -> str:
        """Dump config to JSON string."""
        from json import dumps

        return dumps(self.dict())

    def yaml(self) -> str:
        """Dump config to YAML string (requires PyYAML)."""
        try:
            from yaml import safe_dump
        except ImportError:  # pragma: no cover
            raise ImportError("Could not import yaml.  Please `pip install PyYAML`.")

        return safe_dump(self.dict())

    @classmethod
    def from_configuration(cls, config: pymmcore.Configuration):
        """Create Configuration (Plus) from pymmcore.Configuration"""
        new = cls()
        for s in range(config.size()):
            new.addSetting(config.getSetting(s))
        return new

    @classmethod
    def create(cls, *args, **kwargs):
        """More flexible init to create a Configuration from:

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
            props = []
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
        if not isinstance(o, Configuration):
            return False
        return o.dict() == self.dict()
