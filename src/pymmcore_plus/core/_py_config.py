"""Python reimplementation of the CMMCore loadSystemConfiguration method.

This could be used to support custom configuration files that provide a super-set
of the commands supported by the CMMCorePlus class. It could, for example, be used
to load non-standard devices with a line like:

PyDevice,Emission,python-module,python-class
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from pymmcore_plus import CFGCommand, CFGGroup

if TYPE_CHECKING:
    from typing import TypeAlias

    from ._mmcore_plus import CMMCorePlus

    Executor: TypeAlias = Callable


def load_system_config(core: CMMCorePlus, file: str) -> None:
    try:
        _load_system_config(core, file)
    except Exception as err1:
        # Unload all devices so as not to leave loaded but uninitialized devices
        # (which are prone to cause a crash when accessed) hanging around.
        from pymmcore_plus._logger import logger

        logger.warning(
            "Unloading all devices after failure to load system configuration: %s",
            str(err1),
        )
        try:
            core.unloadAllDevices()
        except Exception as err2:
            logger.error("Error occurred while unloading all devices: %s", str(err2))

        raise err1


def _exec_Device(
    core: CMMCorePlus, label: str, moduleName: str, deviceName: str
) -> None:
    core.loadDevice(label, moduleName, deviceName)


def _exec_PyDevice(core: CMMCorePlus, label: str, module: str, class_name: str) -> None:
    core.load_py_device(label, module, class_name)


def _exec_Property(
    core: CMMCorePlus, label: str, propName: str, propValue: str = ""
) -> None:
    core.setProperty(label, propName, propValue)


def _exec_Label(
    core: CMMCorePlus, stateDeviceLabel: str, state: str, stateLabel: str
) -> None:
    core.defineStateLabel(stateDeviceLabel, int(state), stateLabel)


def _exec_ConfigGroup(core: CMMCorePlus, groupName: str, *args: str) -> None:
    if len(args) == 4:
        core.defineConfig(groupName, *args)
    elif len(args) == 3:
        core.defineConfig(groupName, *args, "")
    else:
        core.defineConfigGroup(groupName)


def _exec_ConfigPixelSize(
    core: CMMCorePlus, resolutionID: str, deviceLabel: str, propName: str, value: str
) -> None:
    core.definePixelSizeConfig(resolutionID, deviceLabel, propName, value)


def _exec_PixelSize_um(core: CMMCorePlus, resolutionID: str, pixSize: str) -> None:
    core.setPixelSizeUm(resolutionID, float(pixSize))


def _exec_PixelSizeAffine(
    core: CMMCorePlus,
    resolutionID: str,
    a1: str,
    a2: str,
    a3: str,
    a4: str,
    a5: str,
    a6: str,
) -> None:
    core.setPixelSizeAffine(resolutionID, list(map(float, (a1, a2, a3, a4, a5, a6))))


def _exec_ParentID(core: CMMCorePlus, deviceLabel: str, parentHubLabel: str) -> None:
    core.setParentLabel(deviceLabel, parentHubLabel)


def _exec_Delay(core: CMMCorePlus, label: str, delayMs: str) -> None:
    core.setDeviceDelayMs(label, float(delayMs))


def _exec_FocusDirection(core: CMMCorePlus, stageLabel: str, sign: str) -> None:
    core.setFocusDirection(stageLabel, int(sign))


COMMAND_EXECUTORS: dict[CFGCommand, Callable] = {
    CFGCommand.PyDevice: _exec_PyDevice,
    CFGCommand.Device: _exec_Device,
    CFGCommand.Label: _exec_Label,
    CFGCommand.Property: _exec_Property,
    CFGCommand.ConfigGroup: _exec_ConfigGroup,
    CFGCommand.Delay: _exec_Delay,
    CFGCommand.ConfigPixelSize: _exec_ConfigPixelSize,
    CFGCommand.PixelSize_um: _exec_PixelSize_um,
    CFGCommand.PixelSizeAffine: _exec_PixelSizeAffine,
    CFGCommand.ParentID: _exec_ParentID,
    CFGCommand.FocusDirection: _exec_FocusDirection,
}
EXPECTED_ARGS = {}
for cmd, executor in COMMAND_EXECUTORS.items():
    max_args = executor.__code__.co_argcount - 1
    min_args = max_args - (len(executor.__defaults__) if executor.__defaults__ else 0)
    EXPECTED_ARGS[cmd] = {min_args, max_args}

# special case
EXPECTED_ARGS[CFGCommand.ConfigGroup] = {1, 4, 5}


def _run_cfg_command(core: CMMCorePlus, line: str) -> None:
    """Run a single line of a system configuration file and apply to the core."""
    try:
        cmd_name, *args = line.split(CFGCommand.FieldDelimiters)
    except ValueError:  # pragma: no cover
        raise ValueError(f"Could not split invalid config line: {line!r}") from None

    try:
        command = CFGCommand(cmd_name)
    except ValueError as exc:
        raise ValueError(f"Unrecognized command name: {cmd_name!r}") from exc

    if command not in COMMAND_EXECUTORS:
        warnings.warn(
            f"Command {cmd_name!r} obsolete or not implemented, skipping.",
            RuntimeWarning,
            stacklevel=2,
        )
        return

    exec_cmd = COMMAND_EXECUTORS[command]
    expected_n_args = EXPECTED_ARGS[command]
    if (nargs := len(args)) not in expected_n_args:
        exp_str = " or ".join(map(str, expected_n_args))
        raise ValueError(
            f"Invalid configuration line encountered for command {cmd_name}. "
            f"Expected {exp_str} arguments, got {nargs}: {line!r}"
        )

    try:
        exec_cmd(core, *args)
    except Exception as exc:
        raise ValueError(f"Error executing command {line!r}: {exc}") from exc


comment_re = re.compile(r"^#(?!PyDevice).*$")


def _load_system_config(core: CMMCorePlus, file: str | Path) -> None:
    """Python reimplementation of the CMMCore loadSystemConfiguration method.

    Args:
        core (CMMCorePlus): The CMMCorePlus instance.
        fileName (str): The file name to load the system configuration from.
    """
    file_path = Path(file).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"File {file_path} does not exist.")

    for line in file_path.read_text().splitlines():
        # if it is a comment or empty line, skip
        # note that comment_re matches comment lines that DON'T have one of
        # our special commands, such as #PyDevice
        if not (line := line.strip()) or comment_re.match(line):
            continue
        if line.startswith("#"):
            # if we made it to this point, it's a special command starting with a #
            # such as #PyDevice
            line = line[1:]
        _run_cfg_command(core, line)

    # force run of internal function updateAllowedChannelGroups
    # might not be necessary
    core.defineConfigGroup("__NOT_A_REAL_GROUP__")
    core.deleteConfigGroup("__NOT_A_REAL_GROUP__")

    # file parsing finished, try to set startup configuration
    if core.isConfigDefined(CFGGroup.System, CFGGroup.System_Startup):
        # We need to build the system state cache once here because setConfig()
        # can fail in certain cases otherwise.
        core.waitForSystem()
        core.updateSystemStateCache()
        core.setConfig(CFGGroup.System, CFGGroup.System_Startup)
    core.waitForSystem()
    core.updateSystemStateCache()
    core.events.systemConfigurationLoaded.emit()


if __name__ == "__main__":
    from pymmcore_plus import CMMCorePlus

    core = CMMCorePlus()

    load_system_config(core, "tests/local_config.cfg")
