from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator, Literal, MutableMapping, overload

import pymmcore

from ._config import Configuration
from ._property import DeviceProperty

if TYPE_CHECKING:
    from ..core._mmcore_plus import CMMCorePlus


class ConfigGroup(MutableMapping[str, Configuration]):
    """Convenience object for dealing with a set of related Configuration objects.

    This object behaves as a [`collections.abc.MutableMapping`][] of `str`
    (configuration group name) to [`Configuration`][pymmcore_plus.Configuration]
    objects.

    It is object type returned by [`pymmcore_plus.CMMCorePlus.getConfigGroupObject`][].

    Parameters
    ----------
    group_name : str
        The name of the configuration group to manage.  (It needn't exist yet)
    mmcore : CMMCorePlus
        The core object managing this config group.
    """

    def __init__(self, group_name: str, mmcore: CMMCorePlus) -> None:
        self._mmc = mmcore
        self._name = group_name

    @property
    def name(self) -> str:
        """Return the name of this ConfigGroup."""
        return self._name

    @property
    def core(self) -> CMMCorePlus:
        """Return the `CMMCorePlus` instance to which this Device is bound."""
        return self._mmc

    def exists(self) -> bool:
        """Return `True` if this ConfigGroup exists in the current configuration."""
        return self._mmc.isGroupDefined(self._name)

    def create(self) -> None:
        """Create this configuration group in core (as an empty group).

        If the group already exists, this is a no-op.
        """
        if not self._mmc.isGroupDefined(self._name):
            self._mmc.defineConfigGroup(self._name)

    def delete(self) -> None:
        """Delete this entire configuration group and all presets in it."""
        self._mmc.deleteConfigGroup(self._name)

    def __contains__(self, configName: object) -> bool:
        """Return `True` if this group already has a preset named `configName`."""
        return (
            self._mmc.isConfigDefined(self._name, configName)
            if isinstance(configName, str)
            else False
        )

    def __delitem__(self, configName: str) -> None:
        self._mmc.deleteConfig(self._name, configName)

    def __getitem__(self, configName: str) -> Configuration:
        try:
            return self._mmc.getConfigData(self._name, configName)
        except ValueError as e:
            if configName not in self:
                raise KeyError(
                    f"Group {self._name!r} does not have a config {configName!r}"
                ) from e
            raise  # pragma: no cover

    def __setitem__(self, configName: str, value: Any) -> None:
        if isinstance(value, (tuple, list)):
            if len(value) != 3:
                raise ValueError("Expected a 3-tuple of (deviceLabel, propName, value)")
            self._mmc.defineConfig(self._name, configName, *value)
        elif isinstance(value, pymmcore.Configuration):
            if configName in self:
                del self[configName]
            for i in range(value.size()):
                ps = value.getSetting(i)
                self._mmc.defineConfig(
                    self._name,
                    configName,
                    ps.getDeviceLabel(),
                    ps.getPropertyName(),
                    ps.getPropertyValue(),
                )
        elif isinstance(value, dict):
            for k in value:
                if not (isinstance(k, tuple) and len(k) == 2):
                    raise ValueError(
                        "Expected a dict of {(deviceLabel, propName): value}"
                    )
            if configName in self:
                del self[configName]
            for k, val in value.items():
                self._mmc.defineConfig(self._name, configName, *k, val)  # type: ignore
        else:
            raise ValueError(
                "Expected a 3-tuple of (deviceLabel, propName, value), "
                "a dict of {(deviceLabel, propName): value}, "
                "or a pymmcore.Configuration object"
            )

    def __iter__(self) -> Iterator[str]:
        yield from self._mmc.getAvailableConfigs(self._name)

    def __len__(self) -> int:
        return len(self._mmc.getAvailableConfigs(self._name))

    def __repr__(self) -> str:
        n_props = len(list(self.iterDeviceProperties()))
        return f"ConfigGroup(presets={list(self)}, n_properties={n_props})"

    def iterDeviceProperties(self) -> Iterator[DeviceProperty]:
        """Iterate `DeviceProperty` for all properties in this ConfigGroup.

        Note, this only iterates over properties that are defined in the first preset of
        this ConfigGroup. This *should* be the same for all presets in this ConfigGroup,
        but it is not guaranteed.  Use `is_consistent` to check if all presets in this
        ConfigGroup have the same properties.
        """
        presets = self._mmc.getAvailableConfigs(self._name)
        if not presets:
            return  # pragma: no cover

        for dev, prop, _ in self._mmc.getConfigData(self._name, presets[0]):
            yield DeviceProperty(dev, prop, self._mmc)

    @property
    def is_consistent(self) -> bool:
        """Return `True` if all presets in this group have the same properties.

        Note that a group with 0 or 1 presets is always considered consistent.  If two
        or more presets are present, they must all have the same device properties.
        (values of course may vary.)
        """
        values = list(self.values())
        if len(values) < 2:
            # A group with 0 or 1 presets is always consistent.
            return True

        return len({frozenset(v[:2] for v in item) for item in values}) == 1

    def renameConfig(self, oldConfigName: str, newConfigName: str) -> None:
        """Rename a configuration in this group.

        If the configuration does not exist, a KeyError is thrown.
        """
        if oldConfigName not in self:
            raise KeyError(
                f"Group {self._name!r} does not have a config {oldConfigName!r}"
            )
        self._mmc.renameConfig(self._name, oldConfigName, newConfigName)

    def setConfig(self, configName: str) -> None:
        """Set the current configuration to `configName`.

        This actually updates the hardware state to match what is stored in the
        preset `configName`.
        """
        self._mmc.setConfig(self._name, configName)

    @overload
    def getCurrentConfig(self, as_object: Literal[True]) -> Configuration:
        ...

    @overload
    def getCurrentConfig(self, as_object: Literal[False] = False) -> str:
        ...

    def getCurrentConfig(self, as_object: bool = False) -> str | Configuration:
        """Returns the current configuration for a given group."""
        current = self._mmc.getCurrentConfig(self._name)
        return self[current] if as_object else current

    @overload
    def getCurrentConfigFromCache(self, as_object: Literal[True]) -> Configuration:
        ...

    @overload
    def getCurrentConfigFromCache(self, as_object: Literal[False] = False) -> str:
        ...

    def getCurrentConfigFromCache(self, as_object: bool = False) -> str | Configuration:
        """Returns the current configuration for a given group from the cache."""
        current = self._mmc.getCurrentConfigFromCache(self._name)
        return self[current] if as_object else current

    def wait(self, configName: str | None = None) -> None:
        """Blocks until all devices included in the configuration group ready.

        If `configName` not provided, then the first configuration in the group is used.
        """
        if configName:
            self._mmc.waitForConfig(self._name, configName)
            return

        presets = self._mmc.getAvailableConfigs(self._name)
        if presets:
            self._mmc.waitForConfig(self._name, presets[0])

    def rename(self, newGroupName: str) -> None:
        """Rename this configuration group."""
        self._mmc.renameConfigGroup(self._name, newGroupName)
        self._name = newGroupName

    def __str__(self) -> str:
        from textwrap import indent

        title = f"ConfigGroup {self._name!r}"
        lines: list[str] = [title, "=" * len(title)]
        for k, v in self.items():
            lines.extend((f"{k}:", indent(str(v), "  ")))
        return "\n".join(lines)
