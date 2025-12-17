"""Config Group Management System.

Distilled from MMCore's config group architecture (MMCore.cpp, ConfigGroup.h,
Configuration.h). This captures the essence of how Micro-Manager manages configuration
presets.

Architecture:
    ConfigGroupCollection (root container)
    └── ConfigGroup["Channel"]          # Named groups of related presets
        └── Configuration["DAPI"]       # Named preset (snapshot of settings)
            └── PropertySetting         # device/prop/value triplet

Key concepts:
    - PropertySetting: Atomic unit - "set <prop> on <device> to <value>"
    - Configuration: A collection of PropertySettings (a "preset" or state snapshot)
    - ConfigGroup: Named collection of presets (e.g., "Channel" group has "DAPI", "GFP"
       presets)
    - ConfigGroupCollection: Top-level container managing all groups

The key algorithm is `get_current_preset()`:
    1. Collect all device/prop pairs referenced by any preset in the group
    2. Read current values from devices for each pair
    3. Check which preset's settings are all contained in the current state
    4. Return first matching preset name (or "" if no match)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Callable


# =============================================================================
# PropertySetting: The atomic unit of configuration
# =============================================================================


@dataclass(frozen=True, slots=True)
class PropertySetting:
    """A single device property value.

    This is the atomic unit of configuration - a triplet that says:
    "Set <prop> on <device> to <value>".

    The key is used for fast lookup: "DeviceLabel-PropertyName"
    """

    device: str
    prop: str  # property name (named 'prop' to avoid shadowing builtin 'property')
    value: str

    @property
    def key(self) -> str:
        """Composite key for indexing: 'device-prop'."""
        return f"{self.device}-{self.prop}"

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.device}.{self.prop}={self.value}"


# =============================================================================
# Configuration: A collection of property settings (a "preset")
# =============================================================================


class Configuration:
    """A named collection of property settings representing a device state snapshot.

    This is what gets stored as a "preset" - e.g., the "DAPI" preset in the
    "Channel" group might contain:
        - Camera.Exposure = 100
        - Dichroic.State = 2
        - EmissionFilter.State = 1

    Supports:
        - Adding/removing settings
        - Checking if another configuration is contained within this one
        - Iteration over settings
    """

    __slots__ = ("_settings",)

    def __init__(self) -> None:
        # Use dict for O(1) lookup by key, preserves insertion order (Python 3.7+)
        self._settings: dict[str, PropertySetting] = {}

    def add(self, setting: PropertySetting) -> None:
        """Add or update a property setting."""
        self._settings[setting.key] = setting

    def remove(self, device: str, prop: str) -> bool:
        """Remove a property setting. Returns True if removed, False if not found."""
        key = f"{device}-{prop}"
        if key in self._settings:
            del self._settings[key]
            return True
        return False

    def get(self, device: str, prop: str) -> PropertySetting | None:
        """Get a specific property setting, or None if not found."""
        return self._settings.get(f"{device}-{prop}")

    def has(self, device: str, prop: str) -> bool:
        """Check if a device/prop pair is in this configuration."""
        return f"{device}-{prop}" in self._settings

    def contains(self, other: Configuration) -> bool:
        """Check if all settings in `other` are present with matching values.

        Used to determine if the current device state matches a preset.
        Returns True if every setting in `other` exists here with the same value.
        """
        for setting in other:
            mine = self._settings.get(setting.key)
            if mine is None or mine.value != setting.value:
                return False
        return True

    def __iter__(self) -> Iterator[PropertySetting]:
        """Iterate over property settings."""
        return iter(self._settings.values())

    def __len__(self) -> int:
        """Return number of property settings."""
        return len(self._settings)

    def __repr__(self) -> str:
        """Return repr string."""
        settings = ", ".join(str(s) for s in self)
        return f"Configuration({settings})"


# =============================================================================
# ConfigGroup: A named collection of configuration presets
# =============================================================================


class ConfigGroup:
    """A group of related configuration presets.

    For example, a "Channel" group might contain presets:
        - "DAPI": blue excitation settings
        - "GFP": green excitation settings
        - "RFP": red excitation settings

    Each preset is a Configuration object containing the property settings.
    """

    __slots__ = ("_configs",)

    def __init__(self) -> None:
        self._configs: dict[str, Configuration] = {}

    def define(
        self,
        preset_name: str,
        device: str | None = None,
        prop: str | None = None,
        value: str | None = None,
    ) -> None:
        """Define a preset, optionally with an initial property setting.

        If the preset doesn't exist, creates it.
        If device/prop/value are provided, adds that setting to the preset.
        """
        if preset_name not in self._configs:
            self._configs[preset_name] = Configuration()

        if device is not None and prop is not None and value is not None:
            self._configs[preset_name].add(PropertySetting(device, prop, value))

    def get(self, preset_name: str) -> Configuration | None:
        """Get a configuration preset by name."""
        return self._configs.get(preset_name)

    def delete(self, preset_name: str) -> bool:
        """Delete a preset. Returns True if deleted, False if not found."""
        if preset_name in self._configs:
            del self._configs[preset_name]
            return True
        return False

    def delete_setting(self, preset_name: str, device: str, prop: str) -> bool:
        """Delete a specific setting from a preset."""
        config = self._configs.get(preset_name)
        if config is None:
            return False
        return config.remove(device, prop)

    def rename(self, old_name: str, new_name: str) -> bool:
        """Rename a preset. Returns True if renamed, False if old doesn't exist."""
        if old_name not in self._configs or new_name in self._configs:
            return False
        self._configs[new_name] = self._configs.pop(old_name)
        return True

    @property
    def presets(self) -> list[str]:
        """List of preset names in this group."""
        return list(self._configs.keys())

    def __contains__(self, preset_name: str) -> bool:
        """Check if preset exists in group."""
        return preset_name in self._configs

    def __len__(self) -> int:
        """Return number of presets in group."""
        return len(self._configs)


# =============================================================================
# ConfigGroupCollection: The top-level container for all config groups
# =============================================================================


class ConfigGroupCollection:
    """Top-level container managing all configuration groups.

    This is the main interface for config group operations.

    Example usage:
        groups = ConfigGroupCollection()

        # Define a channel group with presets
        groups.define("Channel", "DAPI", "Dichroic", "Label", "DAPI-Dichroic")
        groups.define("Channel", "DAPI", "Camera", "Exposure", "100")
        groups.define("Channel", "GFP", "Dichroic", "Label", "GFP-Dichroic")

        # Get available groups and presets
        groups.group_names  # ["Channel"]
        groups.preset_names("Channel")  # ["DAPI", "GFP"]

        # Retrieve a configuration
        config = groups.get("Channel", "DAPI")
    """

    __slots__ = ("_groups",)

    def __init__(self) -> None:
        self._groups: dict[str, ConfigGroup] = {}

    # -------------------------------------------------------------------------
    # Group-level operations
    # -------------------------------------------------------------------------

    def define_group(self, group_name: str) -> bool:
        """Create an empty group. Returns False if group already exists."""
        if group_name in self._groups:
            return False
        self._groups[group_name] = ConfigGroup()
        return True

    def delete_group(self, group_name: str) -> bool:
        """Delete an entire group. Returns False if group doesn't exist."""
        if group_name not in self._groups:
            return False
        del self._groups[group_name]
        return True

    def rename_group(self, old_name: str, new_name: str) -> bool:
        """Rename a group. Returns False if old doesn't exist or new exists."""
        if old_name not in self._groups or new_name in self._groups:
            return False
        self._groups[new_name] = self._groups.pop(old_name)
        return True

    def has_group(self, group_name: str) -> bool:
        """Check if a group exists."""
        return group_name in self._groups

    @property
    def group_names(self) -> list[str]:
        """List of all group names."""
        return list(self._groups.keys())

    # -------------------------------------------------------------------------
    # Preset-level operations
    # -------------------------------------------------------------------------

    def define(
        self,
        group_name: str,
        preset_name: str | None = None,
        device: str | None = None,
        prop: str | None = None,
        value: str | None = None,
    ) -> None:
        """Define a preset within a group, optionally with a property setting.

        Creates the group if it doesn't exist.
        Creates the preset if it doesn't exist.
        Adds the property setting if device/prop/value are provided.

        This is the primary method for building configuration presets.
        """
        # Ensure group exists
        if group_name not in self._groups:
            self._groups[group_name] = ConfigGroup()

        # If no preset specified, just create the group
        if preset_name is None:
            return

        # Define the preset (with optional setting)
        self._groups[group_name].define(preset_name, device, prop, value)

    def get(self, group_name: str, preset_name: str) -> Configuration | None:
        """Get a configuration preset."""
        group = self._groups.get(group_name)
        if group is None:
            return None
        return group.get(preset_name)

    def has_preset(self, group_name: str, preset_name: str) -> bool:
        """Check if a preset exists within a group."""
        return self.get(group_name, preset_name) is not None

    def delete_preset(self, group_name: str, preset_name: str) -> bool:
        """Delete a preset from a group."""
        group = self._groups.get(group_name)
        if group is None:
            return False
        return group.delete(preset_name)

    def delete_setting(
        self, group_name: str, preset_name: str, device: str, prop: str
    ) -> bool:
        """Delete a specific property setting from a preset."""
        group = self._groups.get(group_name)
        if group is None:
            return False
        return group.delete_setting(preset_name, device, prop)

    def rename_preset(self, group_name: str, old_name: str, new_name: str) -> bool:
        """Rename a preset within a group."""
        group = self._groups.get(group_name)
        if group is None:
            return False
        return group.rename(old_name, new_name)

    def preset_names(self, group_name: str) -> list[str]:
        """Get list of preset names in a group."""
        group = self._groups.get(group_name)
        if group is None:
            return []
        return group.presets

    # -------------------------------------------------------------------------
    # Current config detection
    # -------------------------------------------------------------------------

    def get_current_preset(
        self,
        group_name: str,
        get_property: Callable[[str, str], str],
    ) -> str:
        """Determine which preset in a group matches the current device state.

        Args:
            group_name: The config group to check
            get_property: Callback to read current device property values.
                Signature: (device_label, property_name) -> value

        Returns
        -------
            The name of the first matching preset, or "" if no match.

        This is the key algorithm for config group state detection:
        1. Get the union of all device/prop pairs across all presets
        2. Read current values for each pair
        3. Check which preset's settings are all contained in current state
        """
        group = self._groups.get(group_name)
        if group is None:
            return ""

        presets = group.presets
        if not presets:
            return ""

        # Build current state for all properties referenced in this group
        current_state = Configuration()
        seen_keys: set[str] = set()

        for preset_name in presets:
            config = group.get(preset_name)
            if config is None:
                continue
            for setting in config:
                if setting.key not in seen_keys:
                    seen_keys.add(setting.key)
                    try:
                        current_value = get_property(setting.device, setting.prop)
                        current_state.add(
                            PropertySetting(setting.device, setting.prop, current_value)
                        )
                    except Exception:
                        # If we can't read a property, skip it
                        pass

        # Find first preset that matches current state
        for preset_name in presets:
            config = group.get(preset_name)
            if config is not None and current_state.contains(config):
                return preset_name

        return ""

    def clear(self) -> None:
        """Remove all groups and presets."""
        self._groups.clear()


# =============================================================================
# DevicePropertySetter Protocol (for type-safe integration)
# =============================================================================


class DevicePropertySetter(Protocol):
    """Protocol for objects that can set device properties.

    This allows ConfigGroupCollection to apply configurations
    without depending on a specific CMMCore implementation.
    """

    def set_property(self, device: str, prop: str, value: str) -> None:
        """Set a device property value."""
        ...

    def get_property(self, device: str, prop: str) -> str:
        """Get a device property value."""
        ...


def apply_configuration(
    config: Configuration,
    setter: DevicePropertySetter,
) -> list[PropertySetting]:
    """Apply a configuration to devices.

    Args:
        config: The configuration to apply
        setter: Object with set_property method to set device values

    Returns
    -------
        List of PropertySettings that failed to apply.
    """
    failed: list[PropertySetting] = []

    for setting in config:
        try:
            setter.set_property(setting.device, setting.prop, setting.value)
        except Exception:
            failed.append(setting)

    # Retry failed properties (handles dependency chains where one property
    # depends on another being set first)
    if failed:
        still_failed: list[PropertySetting] = []
        for setting in failed:
            try:
                setter.set_property(setting.device, setting.prop, setting.value)
            except Exception:
                still_failed.append(setting)
        failed = still_failed

    return failed


# =============================================================================
# CMMCore: Example showing how config group methods integrate with the Core
# =============================================================================


class CMMCore:
    """Distilled example of how CMMCore manages config groups.

    This shows how all config-group related methods in MMCore.cpp would
    use the ConfigGroupCollection system. Method names use camelCase to
    match the C++ API.

    Key members:
        configGroups_: The ConfigGroupCollection storing all group/preset definitions
        stateCache_: A Configuration caching last-known device property values

    The C++ code also has:
        - deviceManager_: For accessing device instances
        - properties_: CorePropertyCollection for "Core" device properties
        - channelGroup_: Currently selected channel group name
    """

    def __init__(self) -> None:
        # Main storage for all config groups and presets
        self._config_groups = ConfigGroupCollection()

        # Cache of last-set/last-read property values (for getCurrentConfigFromCache)
        self._state_cache = Configuration()

        # The currently selected channel group (a core property)
        self.channelGroup_ = ""

    # -------------------------------------------------------------------------
    # Group-level operations (MMCore.cpp lines 4934-4982)
    # -------------------------------------------------------------------------

    def defineConfigGroup(self, groupName: str) -> None:
        """Create a new empty configuration group.

        C++: MMCore.cpp:4934-4945
        """
        if not self._config_groups.define_group(groupName):
            raise ValueError(f"Group '{groupName}' already exists")
        self._updateAllowedChannelGroups()

    def deleteConfigGroup(self, groupName: str) -> None:
        """Delete an entire configuration group and all its presets.

        C++ MMCore.cpp:4950-4961
        """
        if not self._config_groups.delete_group(groupName):
            raise ValueError(f"Group '{groupName}' does not exist")
        self._updateAllowedChannelGroups()

    def renameConfigGroup(self, oldGroupName: str, newGroupName: str) -> None:
        """Rename a configuration group.

        C++: MMCore.cpp:4966-4982
        """
        if not self._config_groups.rename_group(oldGroupName, newGroupName):
            raise ValueError(f"Group '{oldGroupName}' does not exist")
        self._updateAllowedChannelGroups()
        # If the renamed group was the channel group, update the reference
        if self.channelGroup_ == oldGroupName:
            self.setChannelGroup(newGroupName)

    def isGroupDefined(self, groupName: str) -> bool:
        """Check if a configuration group exists.

        C++: MMCore.cpp:6016-6022
        """
        return self._config_groups.has_group(groupName)

    def getAvailableConfigGroups(self) -> list[str]:
        """Get list of all configuration group names.

        C++: MMCore.cpp:5396-5399
        """
        return self._config_groups.group_names

    # -------------------------------------------------------------------------
    # Preset-level operations (MMCore.cpp lines 4991-5364)
    # -------------------------------------------------------------------------

    def defineConfig(
        self,
        groupName: str,
        configName: str,
        deviceLabel: str | None = None,
        propName: str | None = None,
        value: str | None = None,
    ) -> None:
        """Define a configuration preset, optionally with a property setting.

        Two overloads in C++:
        - defineConfig(group, config) - create empty preset
        - defineConfig(group, config, device, prop, value) - add property

        C++: MMCore.cpp:4991-5042
        """
        group_existed = self._config_groups.has_group(groupName)
        self._config_groups.define(groupName, configName, deviceLabel, propName, value)
        if not group_existed:
            self._updateAllowedChannelGroups()

    def deleteConfig(
        self,
        groupName: str,
        configName: str,
        deviceLabel: str | None = None,
        propName: str | None = None,
    ) -> None:
        """Delete a preset or a specific property from a preset.

        Two overloads in C++:
        - deleteConfig(group, config) - delete entire preset
        - deleteConfig(group, config, device, prop) - delete one property

        C++: MMCore.cpp:5320-5364
        """
        if deviceLabel is not None and propName is not None:
            # Delete specific property from preset
            if not self._config_groups.delete_setting(
                groupName, configName, deviceLabel, propName
            ):
                raise ValueError(f"Property '{propName}' not in preset '{configName}'")
        else:
            # Delete entire preset
            if not self._config_groups.delete_preset(groupName, configName):
                raise ValueError(f"Preset '{configName}' does not exist")

    def renameConfig(
        self, groupName: str, oldConfigName: str, newConfigName: str
    ) -> None:
        """Rename a configuration preset within a group.

        C++: MMCore.cpp:5298-5313
        """
        renamed = self._config_groups.rename_preset(
            groupName, oldConfigName, newConfigName
        )
        if not renamed:
            raise ValueError(f"Preset '{oldConfigName}' does not exist")

    def isConfigDefined(self, groupName: str, configName: str) -> bool:
        """Check if a configuration preset exists.

        C++: MMCore.cpp:6003-6009
        """
        return self._config_groups.has_preset(groupName, configName)

    def getAvailableConfigs(self, configGroup: str) -> list[str]:
        """Get list of preset names in a configuration group.

        C++: MMCore.cpp:5377-5390
        """
        return self._config_groups.preset_names(configGroup)

    def getConfigData(self, configGroup: str, configName: str) -> Configuration:
        """Get the Configuration object for a preset.

        C++: MMCore.cpp:5475-5493
        """
        config = self._config_groups.get(configGroup, configName)
        if config is None:
            raise ValueError(
                f"Group '{configGroup}' or preset '{configName}' does not exist"
            )
        return config

    # -------------------------------------------------------------------------
    # Applying configurations (MMCore.cpp lines 5264-5291, 8094-8185)
    # -------------------------------------------------------------------------

    def setConfig(self, groupName: str, configName: str) -> None:
        """Apply a configuration preset to the system.

        This is the main method users call to switch presets.

        C++: MMCore.cpp:5264-5291
        """
        config = self._config_groups.get(groupName, configName)
        if config is None:
            raise ValueError(f"Preset '{configName}' does not exist in '{groupName}'")
        self.applyConfiguration(config)

    def applyConfiguration(self, config: Configuration) -> None:
        """Apply a Configuration object to devices.

        For each PropertySetting in the config:
        1. If device is "Core", handle as core property
        2. Otherwise, set the property on the device
        3. Update the state cache

        Failed properties are retried once (handles dependency chains).

        C++: MMCore.cpp:8094-8185
        """
        failed: list[PropertySetting] = []

        for setting in config:
            if setting.device == "Core":
                # Special handling for core properties (not shown here)
                self._setCoreProperty(setting.prop, setting.value)
            else:
                try:
                    self._setDeviceProperty(setting.device, setting.prop, setting.value)
                except Exception:
                    failed.append(setting)
            # Update cache on success
            self._state_cache.add(setting)

        # Retry failed properties (dependency resolution)
        if failed:
            errors: list[str] = []
            for setting in failed:
                try:
                    self._setDeviceProperty(setting.device, setting.prop, setting.value)
                    self._state_cache.add(setting)
                except Exception as e:
                    errors.append(f"{setting}: {e}")
            if errors:
                raise RuntimeError("Failed to apply: " + "; ".join(errors))

    # -------------------------------------------------------------------------
    # Current config detection (MMCore.cpp lines 5419-5468)
    # -------------------------------------------------------------------------

    def getCurrentConfig(self, groupName: str) -> str:
        """Get the name of the currently active preset (reading live from devices).

        Iterates through all presets in the group and returns the first one
        whose settings all match the current device state.

        C++: MMCore.cpp:5419-5438
        """
        return self._config_groups.get_current_preset(groupName, self.getProperty)

    def getCurrentConfigFromCache(self, groupName: str) -> str:
        """Get the name of the currently active preset (using cached values).

        Same as getCurrentConfig but reads from stateCache_ instead of devices.
        Faster but may be stale.

        C++: MMCore.cpp:5449-5468
        """
        return self._config_groups.get_current_preset(
            groupName, self.getPropertyFromCache
        )

    # -------------------------------------------------------------------------
    # State queries (MMCore.cpp lines 525-608)
    # -------------------------------------------------------------------------

    def getConfigState(self, group: str, config: str) -> Configuration:
        """Get current device values for properties in a specific preset.

        Returns a Configuration with current values for each property
        defined in the preset.

        C++: MMCore.cpp:525-538
        """
        cfg_data = self.getConfigData(group, config)
        state = Configuration()
        for setting in cfg_data:
            value = self.getProperty(setting.device, setting.prop)
            state.add(PropertySetting(setting.device, setting.prop, value))
        return state

    def getConfigGroupState(self, group: str) -> Configuration:
        """Get current device values for all properties in a group (live).

        Returns a Configuration containing the union of all device/property
        pairs referenced by any preset in the group, with current values.

        C++: MMCore.cpp:545-548, 563-608
        """
        return self._getConfigGroupState(group, from_cache=False)

    def getConfigGroupStateFromCache(self, group: str) -> Configuration:
        """Get cached values for all properties in a group.

        Same as getConfigGroupState but reads from cache.

        C++: MMCore.cpp:554-557
        """
        return self._getConfigGroupState(group, from_cache=True)

    def _getConfigGroupState(self, group: str, from_cache: bool) -> Configuration:
        """Internal: get group state from devices or cache.

        C++: MMCore.cpp:563-608
        """
        presets = self.getAvailableConfigs(group)
        state = Configuration()
        seen_keys: set[str] = set()

        for preset_name in presets:
            preset = self.getConfigData(group, preset_name)
            for setting in preset:
                if setting.key not in seen_keys:
                    seen_keys.add(setting.key)
                    if from_cache:
                        value = self.getPropertyFromCache(setting.device, setting.prop)
                    else:
                        value = self.getProperty(setting.device, setting.prop)
                    state.add(PropertySetting(setting.device, setting.prop, value))

        return state

    # -------------------------------------------------------------------------
    # Cache operations (MMCore.cpp lines 301-307, 1130-1138)
    # -------------------------------------------------------------------------

    def getSystemStateCache(self) -> Configuration:
        """Get the entire system state cache.

        C++: MMCore.cpp:301 (getSystemStateCache)
        """
        return self._state_cache

    def updateSystemStateCache(self) -> None:
        """Refresh the state cache by reading all device properties.

        In C++, this iterates through all devices and reads all properties.
        Here we just show the concept.

        C++: MMCore.cpp:1130-1138
        """
        # In real implementation: iterate all devices, read all properties
        # self.stateCache_ = self.getSystemState()
        pass

    def getPropertyFromCache(self, deviceLabel: str, propName: str) -> str:
        """Get a property value from the cache.

        C++: MMCore.cpp:303-305 (getPropertyFromCache)
        """
        setting = self._state_cache.get(deviceLabel, propName)
        if setting is None:
            raise ValueError(f"Property '{propName}' not in cache for '{deviceLabel}'")
        return setting.value

    # -------------------------------------------------------------------------
    # Channel group (MMCore.cpp lines 283, 292)
    # -------------------------------------------------------------------------

    def getChannelGroup(self) -> str:
        """Get the current channel group name.

        C++: MMCore.cpp:283
        """
        return self.channelGroup_

    def setChannelGroup(self, channelGroup: str) -> None:
        """Set the current channel group.

        C++: MMCore.cpp:292
        """
        self.channelGroup_ = channelGroup

    # -------------------------------------------------------------------------
    # Internal helpers (stubs - would connect to actual device layer)
    # -------------------------------------------------------------------------

    def _updateAllowedChannelGroups(self) -> None:
        """Update the allowed values for the ChannelGroup core property.

        C++: MMCore.cpp:8229-8240
        """
        # In C++: updates properties_->AddAllowedValue for ChannelGroup
        # If current channel group no longer exists, clear it
        if not self.isGroupDefined(self.channelGroup_):
            self.setChannelGroup("")

    def getProperty(self, deviceLabel: str, propName: str) -> str:
        """Get a property value from a device (stub).

        In real implementation, this calls deviceManager_->GetDevice()->GetProperty()
        """
        raise NotImplementedError("Connect to actual device layer")

    def _setDeviceProperty(self, deviceLabel: str, propName: str, value: str) -> None:
        """Set a property on a device (stub).

        In real implementation, this calls deviceManager_->GetDevice()->SetProperty()
        """
        raise NotImplementedError("Connect to actual device layer")

    def _setCoreProperty(self, propName: str, value: str) -> None:
        """Set a core property (stub).

        In real implementation, this calls properties_->Execute()
        """
        raise NotImplementedError("Connect to core property layer")
