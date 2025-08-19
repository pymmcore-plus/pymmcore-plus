from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable

from IPython import get_ipython  # pyright: ignore
from IPython.core.completer import SimpleCompletion, context_matcher

from pymmcore_plus import CMMCorePlus, DeviceType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from IPython.core.completer import (
        CompletionContext,
        SimpleMatcherResult,
    )
    from IPython.core.interactiveshell import InteractiveShell

    # functions that only require the CMMCorePlus instance to return completions
    CoreCompleter = Callable[[CMMCorePlus], Sequence[SimpleCompletion]]
    # functions that require the CMMCorePlus instance and a label to return completions
    CoreLabelCompleter = Callable[[CMMCorePlus, str], Sequence[SimpleCompletion]]


def _get_argument_index(src: str, ns: dict[str, object]) -> int:
    """Parse argument index from method call string.

    Uses a simple comma-counting approach that works reliably across
    different backends (pymmcore, pymmcore-nano, etc.) without relying
    on jedi's ability to understand method signatures.
    """
    p0 = src.rfind("(") + 1
    p1 = src.rfind(")") if ")" in src else None
    if inner := src[slice(p0, p1)].strip():
        # split on commas that are not inside quotes
        return len(inner.split(",")) - 1  # 0-based
    return 0


# matches "obj.attr(" ... note trailing paren
OBJ_METHOD_RE = re.compile(r"(?P<obj>[A-Za-z_][\w\.]*)\s*\.\s*(?P<attr>\w+)\s*\(")


def _null() -> SimpleMatcherResult:
    return {"completions": [], "matched_fragment": "", "suppress": False}


def _dev_labels(
    core: CMMCorePlus, *dev_types: DeviceType, with_null: bool = False
) -> Sequence[SimpleCompletion]:
    try:
        if not dev_types:
            labels = list(core.getLoadedDevices())
        else:
            labels = [
                d
                for dev_type in dev_types
                for d in core.getLoadedDevicesOfType(dev_type)
            ]
        completions = [SimpleCompletion(f'"{lbl}"') for lbl in labels]
        if with_null:
            completions.append(SimpleCompletion("''"))
        return completions
    except Exception:  # pragma: no cover
        return []


def _config_group_names(core: CMMCorePlus) -> Sequence[SimpleCompletion]:
    """Get the names of all configuration groups."""
    try:
        return [
            SimpleCompletion(f'"{name}"') for name in core.getAvailableConfigGroups()
        ]
    except Exception:  # pragma: no cover
        return []


def _config_preset_names(core: CMMCorePlus, group: str) -> Sequence[SimpleCompletion]:
    """Get the names of all configuration presets for a given group."""
    try:
        return [
            SimpleCompletion(f'"{name}"') for name in core.getAvailableConfigs(group)
        ]
    except Exception:  # pragma: no cover
        return []


# fmt: off
# map of (method_name, arg_index) -> function that returns possible completions
CORE_COMPLETERS: dict[tuple[str, int], CoreCompleter] = {
    # ROLES -----------------------------------------------------------------------
    ("setAutoFocusDevice", 0): lambda core: _dev_labels(core, DeviceType.AutoFocus, with_null=True),  # noqa
    ("setCameraDevice", 0): lambda core: _dev_labels(core, DeviceType.Camera, with_null=True),  # noqa
    ("setFocusDevice", 0): lambda core: _dev_labels(core, DeviceType.Stage, with_null=True),  # noqa
    ("setGalvoDevice", 0): lambda core: _dev_labels(core, DeviceType.Galvo, with_null=True),  # noqa
    ("setImageProcessorDevice", 0): lambda core: _dev_labels(core, DeviceType.ImageProcessor, with_null=True),  # noqa
    ("setShutterDevice", 0): lambda core: _dev_labels(core, DeviceType.Shutter, with_null=True),  # noqa
    ("setSLMDevice", 0): lambda core: _dev_labels(core, DeviceType.SLM, with_null=True),
    ("setXYStageDevice", 0): lambda core: _dev_labels(core, DeviceType.XYStage, with_null=True),  # noqa
    # -----------------------
    ("getFocusDirection", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    ("getPosition", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    ("getStageSequenceMaxLength", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    ("home", 0): lambda core: _dev_labels(core, DeviceType.Stage, DeviceType.XYStage),
    ("isContinuousFocusDrive", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    ("isStageLinearSequenceable", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    ("isStageSequenceable", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    ("loadStageSequence", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    ("setAdapterOrigin", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    ("setFocusDirection", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    ("setOrigin", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    ("setPosition", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    ("setRelativePosition", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    ("setStageLinearSequence", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    ("startStageSequence", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    ("stop", 0): lambda core: _dev_labels(core, DeviceType.Stage, DeviceType.XYStage),
    ("stopStageSequence", 0): lambda core: _dev_labels(core, DeviceType.Stage),
    # --------------------
    ("getXPosition", 0): lambda core: _dev_labels(core, DeviceType.XYStage),
    ("getXYPosition", 0): lambda core: _dev_labels(core, DeviceType.XYStage),
    ("getXYStageSequenceMaxLength", 0): lambda core: _dev_labels(core, DeviceType.XYStage),  # noqa
    ("getYPosition", 0): lambda core: _dev_labels(core, DeviceType.XYStage),
    ("isXYStageSequenceable", 0): lambda core: _dev_labels(core, DeviceType.XYStage),
    ("loadXYStageSequence", 0): lambda core: _dev_labels(core, DeviceType.XYStage),
    ("setAdapterOriginXY", 0): lambda core: _dev_labels(core, DeviceType.XYStage),
    ("setOriginX", 0): lambda core: _dev_labels(core, DeviceType.XYStage),
    ("setOriginXY", 0): lambda core: _dev_labels(core, DeviceType.XYStage),
    ("setOriginY", 0): lambda core: _dev_labels(core, DeviceType.XYStage),
    ("setRelativeXYPosition", 0): lambda core: _dev_labels(core, DeviceType.XYStage),
    ("setXYPosition", 0): lambda core: _dev_labels(core, DeviceType.XYStage),
    ("startXYStageSequence", 0): lambda core: _dev_labels(core, DeviceType.XYStage),
    ("stopXYStageSequence", 0): lambda core: _dev_labels(core, DeviceType.XYStage),
    # --------------------
    ("deleteConfig", 2): _dev_labels,
    ("detectDevice", 0): _dev_labels,
    ("deviceBusy", 0): _dev_labels,
    ("getAllowedPropertyValues", 0): _dev_labels,
    ("getDeviceDelayMs", 0): _dev_labels,
    ("getDeviceDescription", 0): _dev_labels,
    ("getDeviceInitializationState", 0): _dev_labels,
    ("getDeviceLibrary", 0): _dev_labels,
    ("getDeviceName", 0): _dev_labels,
    ("getDevicePropertyNames", 0): _dev_labels,
    ("getDeviceType", 0): _dev_labels,
    ("getParentLabel", 0): _dev_labels,
    ("getProperty", 0): _dev_labels,
    ("getPropertyFromCache", 0): _dev_labels,
    ("getPropertyLowerLimit", 0): _dev_labels,  # ?
    ("getPropertySequenceMaxLength", 0): _dev_labels,  # ?
    ("getPropertyType", 0): _dev_labels,
    ("getPropertyUpperLimit", 0): _dev_labels,  # ?
    ("hasProperty", 0): _dev_labels,
    ("hasPropertyLimits", 0): _dev_labels,
    ("initializeDevice", 0): _dev_labels,
    ("isPropertyPreInit", 0): _dev_labels,
    ("isPropertyReadOnly", 0): _dev_labels,
    ("isPropertySequenceable", 0): _dev_labels,
    ("loadPropertySequence", 0): _dev_labels,  # ?
    ("setDeviceDelayMs", 0): _dev_labels,
    ("setParentLabel", 0): _dev_labels,
    ("setProperty", 0): _dev_labels,
    ("startPropertySequence", 0): _dev_labels,  # ?
    ("unloadDevice", 0): _dev_labels,
    ("usesDeviceDelay", 0): _dev_labels,
    ("waitForDevice", 0): _dev_labels,
    # --------------------
    ("displaySLMImage", 0): lambda core: _dev_labels(core, DeviceType.SLM),
    ("getSLMBytesPerPixel", 0): lambda core: _dev_labels(core, DeviceType.SLM),
    ("getSLMExposure", 0): lambda core: _dev_labels(core, DeviceType.SLM),
    ("getSLMHeight", 0): lambda core: _dev_labels(core, DeviceType.SLM),
    ("getSLMNumberOfComponents", 0): lambda core: _dev_labels(core, DeviceType.SLM),
    ("getSLMSequenceMaxLength", 0): lambda core: _dev_labels(core, DeviceType.SLM),
    ("getSLMWidth", 0): lambda core: _dev_labels(core, DeviceType.SLM),
    ("loadSLMSequence", 0): lambda core: _dev_labels(core, DeviceType.SLM),
    ("setSLMExposure", 0): lambda core: _dev_labels(core, DeviceType.SLM),
    ("setSLMImage", 0): lambda core: _dev_labels(core, DeviceType.SLM),
    ("setSLMPixelsTo", 0): lambda core: _dev_labels(core, DeviceType.SLM),
    ("startSLMSequence", 0): lambda core: _dev_labels(core, DeviceType.SLM),
    ("stopSLMSequence", 0): lambda core: _dev_labels(core, DeviceType.SLM),
    # --------------------
    ("deleteGalvoPolygons", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    ("getGalvoChannels", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    ("getGalvoPosition", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    ("getGalvoXMinimum", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    ("getGalvoXRange", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    ("getGalvoYMinimum", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    ("getGalvoYRange", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    ("loadGalvoPolygons", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    ("pointGalvoAndFire", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    ("runGalvoPolygons", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    ("runGalvoSequence", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    ("setGalvoIlluminationState", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    ("setGalvoPolygonRepetitions", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    ("setGalvoPosition", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    ("setGalvoSpotInterval", 0): lambda core: _dev_labels(core, DeviceType.Galvo),
    # --------------------
    ("getExposure", 0): lambda core: _dev_labels(core, DeviceType.Camera),
    ("getExposureSequenceMaxLength", 0): lambda core: _dev_labels(core, DeviceType.Camera),  # noqa
    ("getROI", 0): lambda core: _dev_labels(core, DeviceType.Camera),
    ("isExposureSequenceable", 0): lambda core: _dev_labels(core, DeviceType.Camera),
    ("isSequenceRunning", 0): lambda core: _dev_labels(core, DeviceType.Camera),
    ("loadExposureSequence", 0): lambda core: _dev_labels(core, DeviceType.Camera),
    ("prepareSequenceAcquisition", 0): lambda core: _dev_labels(core, DeviceType.Camera),  # noqa
    ("setExposure", 0): lambda core: _dev_labels(core, DeviceType.Camera),
    ("setROI", 0): lambda core: _dev_labels(core, DeviceType.Camera),
    ("startExposureSequence", 0): lambda core: _dev_labels(core, DeviceType.Camera),
    ("startSequenceAcquisition", 0): lambda core: _dev_labels(core, DeviceType.Camera),
    ("stopExposureSequence", 0): lambda core: _dev_labels(core, DeviceType.Camera),
    ("stopSequenceAcquisition", 0): lambda core: _dev_labels(core, DeviceType.Camera),
    # --------------------
    ("defineStateLabel", 0): lambda core: _dev_labels(core, DeviceType.State),
    ("getNumberOfStates", 0): lambda core: _dev_labels(core, DeviceType.State),
    ("getState", 0): lambda core: _dev_labels(core, DeviceType.State),
    ("getStateFromLabel", 0): lambda core: _dev_labels(core, DeviceType.State),
    ("getStateLabel", 0): lambda core: _dev_labels(core, DeviceType.State),
    ("getStateLabels", 0): lambda core: _dev_labels(core, DeviceType.State),
    ("setState", 0): lambda core: _dev_labels(core, DeviceType.State),
    ("setStateLabel", 0): lambda core: _dev_labels(core, DeviceType.State),
    # --------------------
    ("getShutterOpen", 0): lambda core: _dev_labels(core, DeviceType.Shutter),
    ("setShutterOpen", 0): lambda core: _dev_labels(core, DeviceType.Shutter),
    # --------------------
    ("getInstalledDeviceDescriptions", 0): lambda core: _dev_labels(core, DeviceType.Hub),  # noqa
    ("getInstalledDevices", 0): lambda core: _dev_labels(core, DeviceType.Hub),
    ("getLoadedPeripheralDevices", 0): lambda core: _dev_labels(core, DeviceType.Hub),
    ("getSerialPortAnswer", 0): lambda core: _dev_labels(core, DeviceType.Serial),
    ("readFromSerialPort", 0): lambda core: _dev_labels(core, DeviceType.Serial),
    ("setParentLabel", 1): lambda core: _dev_labels(core, DeviceType.Hub),

    # ----------------- Config Groups --------------------
    ("deleteConfig", 0): _config_group_names,
    ("deleteConfigGroup", 0): _config_group_names,
    ("getAvailableConfigs", 0): _config_group_names,
    ("getConfigData", 0): _config_group_names,
    ("getConfigGroupState", 0): _config_group_names,
    ("getConfigGroupStateFromCache", 0): _config_group_names,
    ("getConfigState", 0): _config_group_names,
    ("getCurrentConfig", 0): _config_group_names,
    ("getCurrentConfigFromCache", 0): _config_group_names,
    ("renameConfig", 0): _config_group_names,
    ("renameConfigGroup", 0): _config_group_names,
    ("setChannelGroup", 0): _config_group_names,
    ("setConfig", 0): _config_group_names,
    ("waitForConfig", 0): _config_group_names,
}
# fmt: on


def _get_prop_names(core: CMMCorePlus, device: str) -> Sequence[SimpleCompletion]:
    """Get the property names for a given device."""
    try:
        return [
            SimpleCompletion(f'"{prop}"')
            for prop in core.getDevicePropertyNames(device)
        ]
    except Exception:  # pragma: no cover
        return []


# fmt: off
# Map of (method_name, arg_index) -> (label arg idx, function that returns completions)
LABEL_COMPLETERS: dict[tuple[str, int], tuple[int, CoreLabelCompleter]] = {
    ("define", 3): (2, _get_prop_names),
    ("definePixelSizeConfig", 2): (1, _get_prop_names),
    ("deleteConfig", 3): (2, _get_prop_names),
    ("getAllowedPropertyValues", 1): (0, _get_prop_names),
    ("getProperty", 1): (0, _get_prop_names),
    ("getPropertyFromCache", 1): (0, _get_prop_names),
    ("getPropertyLowerLimit", 1): (0, _get_prop_names),
    ("getPropertySequenceMaxLength", 1): (0, _get_prop_names),
    ("getPropertyType", 1): (0, _get_prop_names),
    ("getPropertyUpperLimit", 1): (0, _get_prop_names),
    ("hasProperty", 1): (0, _get_prop_names),
    ("hasPropertyLimits", 1): (0, _get_prop_names),
    ("isPropertyPreInit", 1): (0, _get_prop_names),
    ("isPropertyReadOnly", 1): (0, _get_prop_names),
    ("isPropertySequenceable", 1): (0, _get_prop_names),
    ("loadPropertySequence", 1): (0, _get_prop_names),
    ("setProperty", 1): (0, _get_prop_names),
    ("startPropertySequence", 1): (0, _get_prop_names),
    ("stopPropertySequence", 1): (0, _get_prop_names),
    # ----------------- Config Presets --------------------
    ("deleteConfig", 1): (0, _config_preset_names),
    ("getConfigData", 1): (0, _config_preset_names),
    ("getConfigState", 1): (0, _config_preset_names),
    ("renameConfig", 1): (0, _config_preset_names),
    ("setConfig", 1): (0, _config_preset_names),
    ("waitForConfig", 1): (0, _config_preset_names),
}
# fmt: on


@context_matcher()  # type: ignore[misc]
def cmmcoreplus_matcher(ctx: CompletionContext) -> SimpleMatcherResult:
    """
    Offer string completions for CMMCorePlus calls such as.

        core.setCameraDevice(<TAB>)
        core.setProperty("CAM", <TAB>)
    """
    if not (ip := get_ipython()):
        return _null()  # pragma: no cover
    ns = ip.user_ns  # live user namespace

    # 1. Extract the object expression and the *real* attribute name syntactically.
    # e.g.: 'core.setCameraDevice('
    src_to_cursor = ctx.full_text[: ctx.cursor_position]
    if not (m := OBJ_METHOD_RE.search(src_to_cursor)):
        return _null()

    # 2. Ensure we're dealing with a CMMCorePlus method
    # e.g. ('core', 'setCameraDevice')
    var_expr, method_name = m.group("obj"), m.group("attr")
    try:
        obj = eval(var_expr, ns)
    except Exception:
        return _null()

    if not isinstance(obj, CMMCorePlus):
        return _null()

    # 3. Get the argument index for the method call.
    arg_index = _get_argument_index(src_to_cursor, ns)

    # 4. Check if we have a specific completion for this method name and arg_index.
    key = (method_name, arg_index)
    if (dev_getter := CORE_COMPLETERS.get(key)) and (completions := dev_getter(obj)):
        # If we have a specific suggestion for this method and arg_index, use it.
        return {"completions": completions, "suppress": True}

    if info := LABEL_COMPLETERS.get(key):
        dev_idx, getter = info
        if dev_label := _get_argument(src_to_cursor, dev_idx):
            if completions := getter(obj, dev_label):
                return {"completions": completions, "suppress": True}

    return _null()


def _get_argument(src: str, index: int) -> str:
    """Parse the argument at the given index from a method call string.

    For example:
    >>> _get_argument("core.getProperty('Camera', ", 0)
    'Camera'
    """
    p0 = src.find("(") + 1
    p1 = src.rfind(")") if ")" in src else None
    if inner := src[slice(p0, p1)].strip():
        args = inner.split(",")
        if index < len(args):
            return args[index].strip().strip("'\"")
    return ""  # pragma: no cover


def install_pymmcore_ipy_completion(shell: InteractiveShell | None = None) -> None:
    """Install the CMMCorePlus completion matcher in the current IPython session."""
    if shell is None and not (shell := get_ipython()):
        return  # pragma: no cover

    if cmmcoreplus_matcher not in shell.Completer.custom_matchers:
        shell.Completer.custom_matchers.append(cmmcoreplus_matcher)
