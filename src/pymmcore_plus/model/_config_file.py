"""Logic for reading and writing MMCore config files."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, Callable

from pymmcore_plus import CFGCommand, DeviceType, FocusDirection, Keyword, _pymmcore
from pymmcore_plus._util import timestamp

from ._config_group import ConfigGroup, ConfigPreset, Setting
from ._device import Device
from ._microscope import Microscope
from ._pixel_size_config import DEFAULT_AFFINE, PixelSizePreset

if TYPE_CHECKING:
    import io
    from collections.abc import Iterable, Sequence
    from typing import TypeAlias

    Executor: TypeAlias = Callable[[Microscope, Sequence[str]], None]

__all__ = ["dump", "load_from_string"]


def load_from_string(text: str, scope: Microscope | None = None) -> Microscope:
    """Load the Microscope from a string."""
    if scope is None:
        scope = Microscope()  # pragma: no cover
    scope.reset()  # should this go here?
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        run_command(line, scope)
    return scope


def dump(scope: Microscope, str_io: io.TextIOBase) -> None:
    for header, lines in CONFIG_SECTIONS.items():
        str_io.write(f"# {header}\n")
        for line in lines(scope):
            str_io.write(line + "\n")
        str_io.write("\n")


# ------------------ Serialization ------------------


def _serialize(*args: Any) -> str:
    """Return a config string for the given args."""
    return CFGCommand.FieldDelimiters.join(map(str, args))


RESET = _serialize(CFGCommand.Property, Keyword.CoreDevice, Keyword.CoreInitialize, 0)
INIT = _serialize(CFGCommand.Property, Keyword.CoreDevice, Keyword.CoreInitialize, 1)


def yield_date(scope: Microscope) -> Iterable[str]:
    yield f"# Date: {timestamp()}\n"


def iter_devices(scope: Microscope) -> Iterable[str]:
    for d in scope.assigned_com_ports:
        yield _serialize(CFGCommand.Device, d.name, d.library, d.adapter_name)
    for d in scope.devices:
        yield _serialize(CFGCommand.Device, d.name, d.library, d.adapter_name)


# NOTE/TODO:
# MMCore.cpp and MMStudio MicroscopeModel do this a bit differently from each other
# MMStudio only writes out the pre-init properties for specific properties that have
# been marked as "setup properties", created by the config wizard.
# MMCore.cpp just writes out all init props.
# So MMCore will generate more verbose config files.  For now, we are matching the
# core behavior... but this has some slightly undesired implications.
# loading and resaving a config file may ADD a bunch of pre-init properties
# that are simply their default values.
def iter_pre_init_props(scope: Microscope) -> Iterable[str]:
    for dev in scope.devices:
        if dev.name == Keyword.CoreDevice:
            # We shouldn't ever get here, since there should be no core device in
            # in model.devices ... but just in case, we don't want to write it out.
            continue  # pragma: no cover
        for p in dev.properties:
            if p.is_pre_init:
                yield _serialize(CFGCommand.Property, p.device_name, p.name, p.value)


def iter_com_port_props(scope: Microscope) -> Iterable[str]:
    for dev in scope.assigned_com_ports:
        for p in dev.properties:
            if p.is_pre_init:
                yield _serialize(CFGCommand.Property, p.device_name, p.name, p.value)


def iter_hub_refs(scope: Microscope) -> Iterable[str]:
    for d in scope.devices:
        if d.parent_label:
            yield _serialize(CFGCommand.ParentID, d.name, d.parent_label)


def iter_delays(scope: Microscope) -> Iterable[str]:
    for d in scope.devices:
        if d.delay_ms:
            yield _serialize(CFGCommand.Delay, d.name, d.delay_ms)


def iter_focus_directions(scope: Microscope) -> Iterable[str]:
    for d in scope.filter_devices(device_type=DeviceType.Stage):
        yield _serialize(CFGCommand.FocusDirection, d.name, d.focus_direction.value)


def iter_labels(scope: Microscope) -> Iterable[str]:
    for d in scope.filter_devices(device_type=DeviceType.State):
        if d.labels:
            yield f"# {d.name}"
            for state, label in enumerate(d.labels):
                if label:
                    yield _serialize(CFGCommand.Label, d.name, state, label)


def iter_config_presets(scope: Microscope) -> Iterable[str]:
    for group in scope.config_groups.values():
        yield f"# Group: {group.name}"
        # empty group record
        if not group.presets:
            yield _serialize(CFGCommand.ConfigGroup, group.name)
            continue

        # normal group records
        for preset in group.presets.values():
            yield f"# Preset: {preset.name}"
            for s in preset.settings:
                yield _serialize(CFGCommand.ConfigGroup, group.name, preset.name, *s)


ROLES = (
    Keyword.CoreCamera,
    Keyword.CoreShutter,
    Keyword.CoreFocus,
    Keyword.CoreAutoShutter,
)


def iter_roles(scope: Microscope) -> Iterable[str]:
    # we want to maintain the order of ROLES... not the order of the properties
    vals = {p.name: p.value for p in scope.core_device.properties if p.name in ROLES}

    for role in ROLES:
        if role in vals and (val := vals[role]):
            yield _serialize(CFGCommand.Property, Keyword.CoreDevice, role, val)


def iter_pixel_size_presets(scope: Microscope) -> Iterable[str]:
    pixels = scope.pixel_size_group
    for p in pixels.presets.values():
        yield f"# Resolution preset: {p.name}"
        for setting in p.settings:
            yield _serialize(CFGCommand.ConfigPixelSize, p.name, *setting)
        yield _serialize(CFGCommand.PixelSize_um, p.name, p.pixel_size_um)
        if p.affine != DEFAULT_AFFINE:
            yield _serialize(CFGCommand.PixelSizeAffine, p.name, *p.affine)
        if p.angle_dxdz and (cmd := getattr(CFGCommand, "PixelSizeAngleDxdz", None)):
            yield _serialize(cmd, p.name, p.angle_dxdz)
        if p.angle_dydz and (cmd := getattr(CFGCommand, "PixelSizeAngleDydz", None)):
            yield _serialize(cmd, p.name, p.angle_dydz)
        if p.optimalz_um and (cmd := getattr(CFGCommand, "PixelSize_OptimalZUm", None)):
            yield _serialize(cmd, p.name, p.optimalz_um)


# Order will determine the order of the sections in the file
# Keys are headers in the config file, and match those in MMCore.cpp
CONFIG_SECTIONS: dict[str, Callable[[Microscope], Iterable[str]]] = {
    "Generated by pymmcore-plus": yield_date,
    "Unload all devices": lambda _: [RESET],
    "Load devices": iter_devices,
    # "Equipment attributes": lambda _: [],  propertyBlockData
    "Pre-initialization properties": iter_pre_init_props,
    "Pre-init settings for COM ports": iter_com_port_props,
    "Hub references": iter_hub_refs,
    "Initialize": lambda _: [INIT],
    "Delays": iter_delays,
    "Stage focus directions": iter_focus_directions,
    "Camera-synchronized devices": lambda _: [],
    "Labels": iter_labels,
    "Configuration presets": iter_config_presets,
}


if _pymmcore.version_info >= (11, 5):
    CONFIG_SECTIONS["PixelSize settings"] = iter_pixel_size_presets
    CONFIG_SECTIONS["Roles"] = iter_roles
else:
    CONFIG_SECTIONS["Roles"] = iter_roles
    CONFIG_SECTIONS["PixelSize settings"] = iter_pixel_size_presets


# ------------------ Deserialization ------------------

# TODO: ... I think the command subclasses are probably overkill here.
# could just use a map of command name to function


def run_command(line: str, scope: Microscope) -> None:
    """Apply a line of a config file to a scope model instance."""
    try:
        cmd_name, *args = line.split(CFGCommand.FieldDelimiters)
    except ValueError:  # pragma: no cover
        raise ValueError(f"Invalid config line: {line!r}") from None

    try:
        command = CFGCommand(cmd_name)
    except ValueError as exc:
        raise ValueError(f"Invalid command name: {cmd_name!r}") from exc

    if command not in COMMAND_EXECUTORS:
        warnings.warn(
            f"Command {cmd_name!r} not implemented", RuntimeWarning, stacklevel=2
        )
        return

    exec_cmd, expected_n_args = COMMAND_EXECUTORS[command]
    should_raise = command in SHOULD_RAISE

    if (nargs := len(args) + 1) not in expected_n_args:
        exp_str = " or ".join(map(str, expected_n_args))
        msg = (
            f"Invalid configuration line encountered for command {cmd_name}. "
            f"Expected {exp_str} arguments, got {nargs}: {line!r}"
        )
        if should_raise:
            raise ValueError(msg)
        else:
            warnings.warn(msg, RuntimeWarning, stacklevel=2)
            return

    try:
        exec_cmd(scope, args)
    except Exception as exc:
        if should_raise:
            raise ValueError(f"Error executing command {line!r}: {exc}") from exc
        warnings.warn(
            f"Failed to execute command {line!r}: {exc}", RuntimeWarning, stacklevel=2
        )


def _exec_Device(scope: Microscope, args: Sequence[str]) -> None:
    """Load a device from the available devices."""
    # TODO: add description from available devices
    name, library, adapter_name = args
    dev = Device(name=name, library=library, adapter_name=adapter_name)
    scope.devices.append(dev)


def _exec_Property(scope: Microscope, args: Sequence[str]) -> None:
    device_name, prop_name, *_value = args
    value = _value[0] if _value else ""
    if device_name == Keyword.CoreDevice and prop_name == Keyword.CoreInitialize:
        try:
            scope.initialized = bool(int(value))
        except (ValueError, TypeError):
            raise ValueError(f"Value {value!r} is not an integer") from None
        return

    dev = next(iter(scope.filter_devices(name=device_name)))
    prop = dev.set_prop_default(prop_name, value, is_pre_init=not scope.initialized)
    prop.value = value


def _exec_Label(scope: Microscope, args: Sequence[str]) -> None:
    device_name, state, label = args
    dev = next(iter(scope.filter_devices(name=device_name)))
    dev.device_type = DeviceType.State
    dev.set_label(state, label)


def _exec_ConfigGroup(scope: Microscope, args: Sequence[str]) -> None:
    group_name, *rest = args  # possible to define simple the group name
    cg = scope.config_groups.setdefault(group_name, ConfigGroup(name=group_name))
    if rest:
        preset_name, device_name, prop_name, *_value = rest
        value = _value[0] if _value else ""
        preset = cg.presets.setdefault(preset_name, ConfigPreset(name=preset_name))
        preset.settings.append(Setting(device_name, prop_name, value))


def _exec_ConfigPixelSize(scope: Microscope, args: Sequence[str]) -> None:
    # NOTE: this is quite similar to _cmd_config_group... maybe refactor?
    preset_name, device_name, prop_name, value = args
    cg = scope.pixel_size_group
    preset = cg.presets.setdefault(preset_name, PixelSizePreset(name=preset_name))
    preset.settings.append(Setting(device_name, prop_name, value))


def _exec_PixelSize_um(scope: Microscope, args: Sequence[str]) -> None:
    preset_name, value = args
    try:
        preset = scope.pixel_size_group.presets[preset_name]
    except KeyError:
        raise ValueError(f"Pixel size preset {preset_name!r} not found") from None

    try:
        preset.pixel_size_um = float(value)
    except ValueError as exc:
        raise ValueError(f"Invalid pixel size: {value}. Expected a float.") from exc


def _exec_PixelSizeAffine(scope: Microscope, args: Sequence[str]) -> None:
    preset_name, *tform = args
    try:
        preset = scope.pixel_size_group.presets[preset_name]
    except KeyError:
        raise ValueError(f"Pixel size preset {preset_name!r} not found") from None

    # TODO: I think zero args is also a valid value for the affine transform
    if len(tform) != 6:  # pragma: no cover
        raise ValueError(f"Expected 6 values for affine transform, got {len(tform)}")

    try:
        preset.affine = tuple(float(v) for v in tform)  # type: ignore
    except ValueError as exc:
        raise ValueError(
            f"Invalid affine transform: {tform!r}. Expected 6 floats."
        ) from exc


def _exec_ParentID(scope: Microscope, args: Sequence[str]) -> None:
    device_name, parent_label = args
    dev = next(iter(scope.filter_devices(name=device_name)))
    dev.parent_label = parent_label
    dev.device_type = DeviceType.Hub
    try:
        next(iter(scope.filter_devices(name=parent_label)))
    except ValueError:  # pragma: no cover
        warnings.warn(
            f"Parent hub {parent_label!r} not found for device {device_name!r}",
            RuntimeWarning,
            stacklevel=2,
        )


def _exec_Delay(scope: Microscope, args: Sequence[str]) -> None:
    device_name, delay_ms = args
    dev = next(iter(scope.filter_devices(name=device_name)))
    try:
        dev.delay_ms = float(delay_ms)
    except ValueError as exc:
        raise ValueError(f"Invalid delay: {delay_ms!r}. Expected a float.") from exc


def _exec_FocusDirection(scope: Microscope, args: Sequence[str]) -> None:
    device_name, direction = args
    dev = next(iter(scope.filter_devices(name=device_name)))
    dev.device_type = DeviceType.Stage
    try:
        dev.focus_direction = FocusDirection(int(direction))
    except (ValueError, TypeError):
        raise ValueError(f"{direction} is not a valid FocusDirection") from None


# expected_nargs INCLUDES the command itself
# e.g. Property,Core,Initialize,1 => 4 args
#                         command -> (executor, expected_n_args)
COMMAND_EXECUTORS: dict[CFGCommand, tuple[Executor, set[int]]] = {
    CFGCommand.Device: (_exec_Device, {4}),
    CFGCommand.Label: (_exec_Label, {4}),
    CFGCommand.Property: (_exec_Property, {3, 4}),
    CFGCommand.ConfigGroup: (_exec_ConfigGroup, {2, 5, 6}),
    CFGCommand.Delay: (_exec_Delay, {3}),
    CFGCommand.ConfigPixelSize: (_exec_ConfigPixelSize, {5}),
    CFGCommand.PixelSize_um: (_exec_PixelSize_um, {3}),
    CFGCommand.PixelSizeAffine: (_exec_PixelSizeAffine, {8}),
    CFGCommand.ParentID: (_exec_ParentID, {3}),
    CFGCommand.FocusDirection: (_exec_FocusDirection, {3}),
}

# Commands that should raise when fail
SHOULD_RAISE = {CFGCommand.Device, CFGCommand.Property}
