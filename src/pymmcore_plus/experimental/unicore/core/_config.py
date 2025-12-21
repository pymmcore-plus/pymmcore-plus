"""Config file loading and saving for UniMMCore.

This module provides Python-owned config file loading/saving that supports
both C++ and Python devices. Python device lines use a `#py ` prefix so they
are treated as comments by upstream C++/pymmcore implementations.

Format example:
    # C++ devices
    Device,Camera,DemoCamera,DCam
    Property,Core,Initialize,1

    # Python devices (hidden from upstream via comment prefix)
    #py pyDevice,PyCamera,mypackage.cameras,MyCameraClass
    #py Property,PyCamera,Exposure,50.0
    #py Property,Core,Camera,PyCamera

    # Config groups can mix both
    ConfigGroup,Channel,DAPI,Dichroic,Label,400DCLP
    #py ConfigGroup,Channel,DAPI,PyFilter,Position,Blue
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from pymmcore_plus import CFGCommand, CFGGroup, DeviceType, Keyword
from pymmcore_plus._util import timestamp

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from ._unicore import UniMMCore

__all__ = ["load_system_configuration", "save_system_configuration"]

# Prefix for Python device lines (treated as comment by C++/regular pymmcore)
PY_PREFIX = "#py "
# Custom command names (not in CFGCommand enum)
_PY_DEVICE_CMD = "pyDevice"


# =============================================================================
# Loading
# =============================================================================


def load_system_configuration(core: UniMMCore, filename: str | Path) -> None:
    """Load system configuration from a file.

    This is a Python implementation of MMCore::loadSystemConfigurationImpl
    that supports both C++ and Python devices. Lines prefixed with `#py `
    are processed as Python device commands.

    Parameters
    ----------
    core : UniMMCore
        The core instance to configure.
    filename : str | Path
        Path to the configuration file.
    """
    path = Path(filename).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    load_from_string(core, path.read_text(), str(path))


def load_from_string(core: UniMMCore, text: str, source: str = "<string>") -> None:
    """Load system configuration from a string.

    Parameters
    ----------
    core : UniMMCore
        The core instance to configure.
    text : str
        The configuration text.
    source : str
        Source identifier for error messages.
    """
    for line_num, line in enumerate(text.splitlines(), start=1):
        # Strip Windows CR if present
        if not (line := line.rstrip("\r").strip()):
            continue

        try:
            # strip #py prefix (python devices)
            if line.startswith(PY_PREFIX):
                line = line[len(PY_PREFIX) :].lstrip()

            if line.startswith("#"):
                # Regular comment - skip
                continue
            else:
                # Standard command
                _run_command(core, line)
        except Exception as e:
            raise RuntimeError(
                f"Error in configuration file {source!r} at line {line_num}: "
                f"{line!r}\n{e}"
            ) from e

    # File parsing finished, apply startup configuration if defined
    if core.isConfigDefined(CFGGroup.System, CFGGroup.System_Startup):
        # Build system state cache before setConfig to avoid failures
        core.waitForSystem()
        core.updateSystemStateCache()
        core.setConfig(CFGGroup.System, CFGGroup.System_Startup)

    # Final sync after all configuration is applied
    core.waitForSystem()
    core.updateSystemStateCache()


def _run_command(core: UniMMCore, line: str) -> None:
    """Execute a single configuration command.

    Mirrors MMCore::loadSystemConfigurationImpl command processing.
    """
    tokens = line.split(CFGCommand.FieldDelimiters)
    if not tokens:
        return

    cmd_name, *args = tokens

    # Handle custom commands first
    if cmd_name == _PY_DEVICE_CMD:
        _exec_device(core, args)
        return

    try:
        command = CFGCommand(cmd_name)
    except ValueError:  # pragma: no cover
        raise ValueError(f"Unknown configuration command: {cmd_name!r}") from None

    if command == CFGCommand.Configuration:  # pragma: no cover
        warnings.warn(
            f"Obsolete command {cmd_name!r} ignored in configuration file",
            UserWarning,
            stacklevel=3,
        )
        return
    if command == CFGCommand.Equipment:  # pragma: no cover
        raise ValueError("Equipment command has been removed from config format")
    if command == CFGCommand.ImageSynchro:  # pragma: no cover
        raise ValueError("ImageSynchro command has been removed from config format")

    executor = _COMMAND_EXECUTORS.get(command)
    if executor is None:  # pragma: no cover
        # Unknown command in our executor map - should not happen for valid CFGCommand
        return

    try:
        executor(core, args)
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            f"Error executing command {cmd_name!r} with arguments {args!r}: {e}"
        ) from e


# =============================================================================
# Command Executors
# =============================================================================


def _exec_device(core: UniMMCore, args: Sequence[str]) -> None:
    """Load a device: Device,<label>,<library>,<device_name>."""
    if len(args) != 3:
        raise ValueError(f"Device command requires 3 arguments, got {len(args)}")
    label, library, device_name = args
    core.loadDevice(label, library, device_name)


def _exec_property(core: UniMMCore, args: Sequence[str]) -> None:
    """Set a property: Property,<device>,<property>,<value>."""
    if len(args) not in (2, 3):
        raise ValueError(f"Property command requires 2-3 arguments, got {len(args)}")

    device, prop = args[0], args[1]
    value = args[2] if len(args) > 2 else ""

    # Special case: Core device properties
    if device == Keyword.CoreDevice:
        if prop == Keyword.CoreInitialize:
            try:
                init_val = int(value)
            except (ValueError, TypeError):
                raise ValueError(
                    f"Initialize value must be integer, got {value!r}"
                ) from None
            if init_val == 0:
                # Unload all devices (reset state for fresh config load)
                core.unloadAllDevices()
            elif init_val == 1:
                core.initializeAllDevices()
            return
        elif prop == Keyword.CoreCamera:
            core.setCameraDevice(value)
            return
        elif prop == Keyword.CoreShutter:
            core.setShutterDevice(value)
            return
        elif prop == Keyword.CoreFocus:
            core.setFocusDevice(value)
            return
        elif prop == Keyword.CoreXYStage:
            core.setXYStageDevice(value)
            return
        elif prop == Keyword.CoreAutoFocus:
            core.setAutoFocusDevice(value)
            return
        elif prop == Keyword.CoreSLM:
            core.setSLMDevice(value)
            return
        elif prop == Keyword.CoreGalvo:
            core.setGalvoDevice(value)
            return
        elif prop == Keyword.CoreChannelGroup:
            core.setChannelGroup(value)
            return
        elif prop == Keyword.CoreAutoShutter:
            core.setAutoShutter(bool(int(value)))
            return

    core.setProperty(device, prop, value)


def _exec_delay(core: UniMMCore, args: Sequence[str]) -> None:
    """Set device delay: Delay,<device>,<delay_ms>."""
    if len(args) != 2:
        raise ValueError(f"Delay command requires 2 arguments, got {len(args)}")
    device, delay_str = args
    try:
        delay_ms = float(delay_str)
    except ValueError:
        raise ValueError(f"Delay must be a number, got {delay_str!r}") from None
    core.setDeviceDelayMs(device, delay_ms)


def _exec_focus_direction(core: UniMMCore, args: Sequence[str]) -> None:
    """Set focus direction: FocusDirection,<device>,<direction>."""
    if len(args) != 2:
        raise ValueError(
            f"FocusDirection command requires 2 arguments, got {len(args)}"
        )
    device, direction_str = args
    try:
        direction = int(direction_str)
    except ValueError:
        raise ValueError(
            f"FocusDirection must be an integer, got {direction_str!r}"
        ) from None
    core.setFocusDirection(device, direction)


def _exec_label(core: UniMMCore, args: Sequence[str]) -> None:
    """Define state label: Label,<device>,<state>,<label>."""
    if len(args) != 3:
        raise ValueError(f"Label command requires 3 arguments, got {len(args)}")
    device, state_str, label = args
    try:
        state = int(state_str)
    except ValueError:
        raise ValueError(f"State must be an integer, got {state_str!r}") from None
    core.defineStateLabel(device, state, label)


def _exec_config_group(core: UniMMCore, args: Sequence[str]) -> None:
    """Define config group/preset."""
    if len(args) < 1:
        raise ValueError("ConfigGroup command requires at least 1 argument")

    group_name = args[0]

    if len(args) == 1:
        # Just define an empty group
        core.defineConfigGroup(group_name)
    elif len(args) in (4, 5):
        # Define a config setting
        preset_name = args[1]
        device = args[2]
        prop = args[3]
        value = args[4] if len(args) > 4 else ""
        core.defineConfig(group_name, preset_name, device, prop, value)
    else:
        raise ValueError(
            f"ConfigGroup command requires 1, 4, or 5 arguments, got {len(args)}"
        )


def _exec_config_pixel_size(core: UniMMCore, args: Sequence[str]) -> None:
    """Define pixel size config: ConfigPixelSize,<preset>,<device>,<prop>,<value>."""
    if len(args) != 4:
        raise ValueError(
            f"ConfigPixelSize command requires 4 arguments, got {len(args)}"
        )
    preset_name, device, prop, value = args
    core.definePixelSizeConfig(preset_name, device, prop, value)


def _exec_pixel_size_um(core: UniMMCore, args: Sequence[str]) -> None:
    """Set pixel size: PixelSize_um,<preset>,<size>."""
    if len(args) != 2:
        raise ValueError(f"PixelSize_um command requires 2 arguments, got {len(args)}")
    preset_name, size_str = args
    try:
        size = float(size_str)
    except ValueError:
        raise ValueError(f"Pixel size must be a number, got {size_str!r}") from None
    core.setPixelSizeUm(preset_name, size)


def _exec_pixel_size_affine(core: UniMMCore, args: Sequence[str]) -> None:
    """Set pixel size affine transform."""
    if len(args) != 7:
        raise ValueError(
            f"PixelSizeAffine command requires 7 arguments, got {len(args)}"
        )
    preset_name = args[0]
    try:
        affine = [float(x) for x in args[1:]]
    except ValueError:
        raise ValueError(f"Affine values must be numbers, got {args[1:]!r}") from None
    core.setPixelSizeAffine(preset_name, affine)


def _exec_parent_id(core: UniMMCore, args: Sequence[str]) -> None:
    """Set parent hub: Parent,<device>,<parent_hub>."""
    if len(args) != 2:
        raise ValueError(f"Parent command requires 2 arguments, got {len(args)}")
    device, parent = args
    core.setParentLabel(device, parent)


# Map commands to their executors
# Commands not in this map are silently ignored (Equipment, ImageSynchro, etc.)
_COMMAND_EXECUTORS: dict[CFGCommand, Callable[[UniMMCore, Sequence[str]], None]] = {
    CFGCommand.Device: _exec_device,
    CFGCommand.Property: _exec_property,
    CFGCommand.Delay: _exec_delay,
    CFGCommand.FocusDirection: _exec_focus_direction,
    CFGCommand.Label: _exec_label,
    CFGCommand.ConfigGroup: _exec_config_group,
    CFGCommand.ConfigPixelSize: _exec_config_pixel_size,
    CFGCommand.PixelSize_um: _exec_pixel_size_um,
    CFGCommand.PixelSizeAffine: _exec_pixel_size_affine,
    CFGCommand.ParentID: _exec_parent_id,
}

# Add optional pixel size commands if available
if hasattr(CFGCommand, "PixelSize_dxdz"):

    def _exec_pixel_size_dxdz(core: UniMMCore, args: Sequence[str]) -> None:
        if len(args) != 2:
            raise ValueError(
                f"PixelSize_dxdz command requires 2 arguments, got {len(args)}"
            )
        preset_name, value_str = args
        core.setPixelSizedxdz(preset_name, float(value_str))

    _COMMAND_EXECUTORS[CFGCommand.PixelSize_dxdz] = _exec_pixel_size_dxdz

if hasattr(CFGCommand, "PixelSize_dydz"):

    def _exec_pixel_size_dydz(core: UniMMCore, args: Sequence[str]) -> None:
        if len(args) != 2:
            raise ValueError(
                f"PixelSize_dydz command requires 2 arguments, got {len(args)}"
            )
        preset_name, value_str = args
        core.setPixelSizedydz(preset_name, float(value_str))

    _COMMAND_EXECUTORS[CFGCommand.PixelSize_dydz] = _exec_pixel_size_dydz

if hasattr(CFGCommand, "PixelSize_OptimalZUm"):

    def _exec_pixel_size_optimal_z(core: UniMMCore, args: Sequence[str]) -> None:
        if len(args) != 2:
            raise ValueError(
                f"PixelSize_OptimalZUm command requires 2 arguments, got {len(args)}"
            )
        preset_name, value_str = args
        core.setPixelSizeOptimalZUm(preset_name, float(value_str))

    _COMMAND_EXECUTORS[CFGCommand.PixelSize_OptimalZUm] = _exec_pixel_size_optimal_z


# =============================================================================
# Saving
# =============================================================================


def save_system_configuration(
    core: UniMMCore, filename: str | Path, *, prefix_py_devices: bool = True
) -> None:
    """Save the current system configuration to a file.

    This saves both C++ and Python devices.

    Parameters
    ----------
    core : UniMMCore
        The core instance to save configuration from.
    filename : str | Path
        Path to save the configuration file.
    prefix_py_devices : bool, optional
        If True (default), Python device lines are prefixed with `#py ` so they
        are ignored by upstream C++/pymmcore implementations. If False, Python
        device lines are saved without the prefix (config will only be loadable
        by UniMMCore).
    """
    path = Path(filename).expanduser().resolve()

    with open(path, "w") as f:
        for section, lines in _iter_config_sections(core, prefix_py_devices):
            f.write(f"# {section}\n")
            for line in lines:
                f.write(line + "\n")
            f.write("\n")


def _serialize(
    *args: Any, py_device: bool = False, prefix_py_devices: bool = True
) -> str:
    """Create a config line from arguments."""
    line = CFGCommand.FieldDelimiters.join(str(a) for a in args)
    return f"{PY_PREFIX}{line}" if (py_device and prefix_py_devices) else line


def _iter_config_sections(
    core: UniMMCore, prefix_py_devices: bool = True
) -> Iterable[tuple[str, Iterable[str]]]:
    """Iterate over config sections, yielding (header, lines) tuples."""
    pfx = prefix_py_devices  # shorthand
    yield f"Generated by pymmcore-plus UniMMCore on {timestamp()}", []

    # Reset command
    yield (
        "Unload all devices",
        [
            _serialize(
                CFGCommand.Property, Keyword.CoreDevice, Keyword.CoreInitialize, 0
            )
        ],
    )

    # Load devices
    yield "Load devices", list(_iter_devices(core, pfx))

    # Pre-initialization properties
    yield "Pre-initialization properties", list(_iter_pre_init_props(core, pfx))

    # Hub references
    yield "Hub references", list(_iter_hub_refs(core))

    # Initialize command
    yield (
        "Initialize",
        [
            _serialize(
                CFGCommand.Property, Keyword.CoreDevice, Keyword.CoreInitialize, 1
            )
        ],
    )

    # Delays
    yield "Delays", list(_iter_delays(core, pfx))

    # Focus directions
    yield "Stage focus directions", list(_iter_focus_directions(core, pfx))

    # Labels
    yield "Labels", list(_iter_labels(core, pfx))

    # Config groups
    yield "Configuration presets", list(_iter_config_groups(core, pfx))

    # Pixel size configs
    yield "PixelSize settings", list(_iter_pixel_size_configs(core, pfx))

    # Core device roles
    yield "Roles", list(_iter_roles(core, pfx))


def _iter_devices(core: UniMMCore, prefix_py_devices: bool = True) -> Iterable[str]:
    """Iterate over device load commands."""
    for label in core.getLoadedDevices():
        if label == Keyword.CoreDevice:  # type: ignore[comparison-overlap]
            continue
        is_py = core.isPyDevice(label)
        library = core.getDeviceLibrary(label)
        device_name = core.getDeviceName(label)
        # Use pyDevice command for Python devices, Device for C++ devices
        cmd = _PY_DEVICE_CMD if is_py else CFGCommand.Device
        yield _serialize(
            cmd,
            label,
            library,
            device_name,
            py_device=is_py,
            prefix_py_devices=prefix_py_devices,
        )


def _iter_pre_init_props(
    core: UniMMCore, prefix_py_devices: bool = True
) -> Iterable[str]:
    """Iterate over pre-initialization property commands."""
    for label in core.getLoadedDevices():
        if label == Keyword.CoreDevice:  # type: ignore[comparison-overlap]
            continue
        is_py = core.isPyDevice(label)
        for prop_name in core.getDevicePropertyNames(label):
            if core.isPropertyPreInit(label, prop_name):
                value = core.getProperty(label, prop_name)
                yield _serialize(
                    CFGCommand.Property,
                    label,
                    prop_name,
                    value,
                    py_device=is_py,
                    prefix_py_devices=prefix_py_devices,
                )


def _iter_hub_refs(core: UniMMCore) -> Iterable[str]:
    """Iterate over parent hub reference commands."""
    for label in core.getLoadedDevices():
        if label == Keyword.CoreDevice:  # type: ignore[comparison-overlap]
            continue
        is_py = core.isPyDevice(label)
        # Python devices don't have parent labels (yet)
        if is_py:
            continue
        try:
            parent = core.getParentLabel(label)
        except RuntimeError:
            continue
        if parent:
            yield _serialize(CFGCommand.ParentID, label, parent, py_device=False)


def _iter_delays(core: UniMMCore, prefix_py_devices: bool = True) -> Iterable[str]:
    """Iterate over device delay commands."""
    for label in core.getLoadedDevices():
        if label == Keyword.CoreDevice:  # type: ignore[comparison-overlap]
            continue
        delay = core.getDeviceDelayMs(label)
        if delay > 0:
            yield _serialize(
                CFGCommand.Delay,
                label,
                delay,
                py_device=core.isPyDevice(label),
                prefix_py_devices=prefix_py_devices,
            )


def _iter_focus_directions(
    core: UniMMCore, prefix_py_devices: bool = True
) -> Iterable[str]:
    """Iterate over focus direction commands."""
    for label in core.getLoadedDevicesOfType(DeviceType.Stage):
        is_py = core.isPyDevice(label)
        direction = core.getFocusDirection(label)
        yield _serialize(
            CFGCommand.FocusDirection,
            label,
            direction.value,
            py_device=is_py,
            prefix_py_devices=prefix_py_devices,
        )


def _iter_labels(core: UniMMCore, prefix_py_devices: bool = True) -> Iterable[str]:
    """Iterate over state device label commands."""
    for label in core.getLoadedDevicesOfType(DeviceType.State):
        is_py = core.isPyDevice(label)
        labels = core.getStateLabels(label)
        for state, state_label in enumerate(labels):
            if state_label:
                yield _serialize(
                    CFGCommand.Label,
                    label,
                    state,
                    state_label,
                    py_device=is_py,
                    prefix_py_devices=prefix_py_devices,
                )


def _iter_config_groups(
    core: UniMMCore, prefix_py_devices: bool = True
) -> Iterable[str]:
    """Iterate over config group commands."""
    for group_name in core.getAvailableConfigGroups():
        presets = core.getAvailableConfigs(group_name)
        if not presets:
            # Empty group
            yield _serialize(CFGCommand.ConfigGroup, group_name)
            continue

        for preset_name in presets:
            config = core.getConfigData(group_name, preset_name, native=True)
            for i in range(config.size()):
                setting = config.getSetting(i)
                device = setting.getDeviceLabel()
                prop = setting.getPropertyName()
                value = setting.getPropertyValue()
                is_py = core.isPyDevice(device)
                yield _serialize(
                    CFGCommand.ConfigGroup,
                    group_name,
                    preset_name,
                    device,
                    prop,
                    value,
                    py_device=is_py,
                    prefix_py_devices=prefix_py_devices,
                )


def _iter_pixel_size_configs(
    core: UniMMCore, prefix_py_devices: bool = True
) -> Iterable[str]:
    """Iterate over pixel size config commands."""
    for preset_name in core.getAvailablePixelSizeConfigs():
        config = core.getPixelSizeConfigData(preset_name, native=True)
        for i in range(config.size()):
            setting = config.getSetting(i)
            device = setting.getDeviceLabel()
            prop = setting.getPropertyName()
            value = setting.getPropertyValue()
            # Pixel size configs typically only reference C++ devices
            is_py = core.isPyDevice(device)
            yield _serialize(
                CFGCommand.ConfigPixelSize,
                preset_name,
                device,
                prop,
                value,
                py_device=is_py,
                prefix_py_devices=prefix_py_devices,
            )

        # Pixel size
        size = core.getPixelSizeUmByID(preset_name)
        yield _serialize(CFGCommand.PixelSize_um, preset_name, size)

        # Affine transform
        affine = core.getPixelSizeAffineByID(preset_name)
        if affine and any(v != 0 for v in affine):
            yield _serialize(CFGCommand.PixelSizeAffine, preset_name, *affine)

        # Optional extended pixel size properties
        if hasattr(core, "getPixelSizedxdz"):
            dxdz = core.getPixelSizedxdz(preset_name)
            if dxdz:
                yield _serialize(CFGCommand.PixelSize_dxdz, preset_name, dxdz)
        if hasattr(core, "getPixelSizedydz"):
            dydz = core.getPixelSizedydz(preset_name)
            if dydz:
                yield _serialize(CFGCommand.PixelSize_dydz, preset_name, dydz)
        if hasattr(core, "getPixelSizeOptimalZUm"):
            optimal_z = core.getPixelSizeOptimalZUm(preset_name)
            if optimal_z:
                yield _serialize(
                    CFGCommand.PixelSize_OptimalZUm, preset_name, optimal_z
                )


def _iter_roles(core: UniMMCore, prefix_py_devices: bool = True) -> Iterable[str]:
    """Iterate over core device role commands."""
    roles = [
        (Keyword.CoreCamera, core.getCameraDevice),
        (Keyword.CoreShutter, core.getShutterDevice),
        (Keyword.CoreFocus, core.getFocusDevice),
        (Keyword.CoreXYStage, core.getXYStageDevice),
        (Keyword.CoreAutoFocus, core.getAutoFocusDevice),
        (Keyword.CoreSLM, core.getSLMDevice),
        (Keyword.CoreGalvo, core.getGalvoDevice),
    ]

    for role_keyword, getter in roles:
        try:
            device = getter()
            if device:
                is_py = core.isPyDevice(device)
                yield _serialize(
                    CFGCommand.Property,
                    Keyword.CoreDevice,
                    role_keyword,
                    device,
                    py_device=is_py,
                    prefix_py_devices=prefix_py_devices,
                )
        except Exception:
            # Some getters may not be available
            pass

    # AutoShutter setting
    auto_shutter = core.getAutoShutter()
    yield _serialize(
        CFGCommand.Property,
        Keyword.CoreDevice,
        Keyword.CoreAutoShutter,
        int(auto_shutter),
    )
