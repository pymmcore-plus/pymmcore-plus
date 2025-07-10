from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable, cast

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

    CoreCompleter = Callable[[CMMCorePlus], Sequence[SimpleCompletion]]
    CoreDeviceCompleter = Callable[[CMMCorePlus, str], Sequence[SimpleCompletion]]

try:
    import jedi

    def _get_argument_index(src: str, ns: dict[str, object]) -> int:
        script = jedi.Interpreter(src, [ns])
        if not (sigs := script.get_signatures()):  # not inside a call
            # unlikely to ever hit due to the OBJ_METHOD_RE check above
            return -1  # pragma: no cover
        return cast("int", sigs[-1].index)

except ImportError:

    def _get_argument_index(src: str, ns: dict[str, object]) -> int:
        p0 = src.rfind("(") + 1
        p1 = src.rfind(")") if ")" in src else None
        if inner := src[slice(p0, p1)].strip():
            # split on commas that are not inside quotes
            return len(inner.split(",")) - 1  # 0-based
        return 0


# matches "obj.attr(" ... note trailing paren
OBJ_METHOD_RE = re.compile(r"(?P<obj>[A-Za-z_][\w\.]*)\s*\.\s*(?P<attr>\w+)\s*\(")


def _null(ctx: CompletionContext) -> SimpleMatcherResult:
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


# fmt: off
# map of (method_name, arg_index) -> function that returns possible completions
DEVICE_COMPLETERS: dict[tuple[str, int], CoreCompleter] = {
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
    ("detectDevice", 0): lambda core: _dev_labels(core),
    ("deviceBusy", 0): lambda core: _dev_labels(core),
    ("getAllowedPropertyValues", 0): lambda core: _dev_labels(core),
    ("getDeviceDelayMs", 0): lambda core: _dev_labels(core),
    ("getDeviceDescription", 0): lambda core: _dev_labels(core),
    ("getDeviceInitializationState", 0): lambda core: _dev_labels(core),
    ("getDeviceLibrary", 0): lambda core: _dev_labels(core),
    ("getDeviceName", 0): lambda core: _dev_labels(core),
    ("getDevicePropertyNames", 0): lambda core: _dev_labels(core),
    ("getDeviceType", 0): lambda core: _dev_labels(core),
    ("getParentLabel", 0): lambda core: _dev_labels(core),
    ("getProperty", 0): lambda core: _dev_labels(core),
    ("getPropertyFromCache", 0): lambda core: _dev_labels(core),
    ("getPropertyLowerLimit", 0): lambda core: _dev_labels(core),  # ?
    ("getPropertySequenceMaxLength", 0): lambda core: _dev_labels(core),  # ?
    ("getPropertyType", 0): lambda core: _dev_labels(core),
    ("getPropertyUpperLimit", 0): lambda core: _dev_labels(core),  # ?
    ("hasProperty", 0): lambda core: _dev_labels(core),
    ("hasPropertyLimits", 0): lambda core: _dev_labels(core),
    ("initializeDevice", 0): lambda core: _dev_labels(core),
    ("isPropertyPreInit", 0): lambda core: _dev_labels(core),
    ("isPropertyReadOnly", 0): lambda core: _dev_labels(core),
    ("isPropertySequenceable", 0): lambda core: _dev_labels(core),
    ("loadPropertySequence", 0): lambda core: _dev_labels(core),  # ?
    ("setDeviceDelayMs", 0): lambda core: _dev_labels(core),
    ("setParentLabel", 0): lambda core: _dev_labels(core),
    ("setProperty", 0): lambda core: _dev_labels(core),
    ("startPropertySequence", 0): lambda core: _dev_labels(core),  # ?
    ("unloadDevice", 0): lambda core: _dev_labels(core),
    ("usesDeviceDelay", 0): lambda core: _dev_labels(core),
    ("waitForDevice", 0): lambda core: _dev_labels(core),
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
    # ----------------- PROPERTY COMPLETIONS --------------------
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
# Map of (method_name, arg_index) -> (device arg idx, function that returns prop names)
PROP_COMPLETERS: dict[tuple[str, int], tuple[int, CoreDeviceCompleter]] = {
    ("define", 3): (2, lambda core, device: _get_prop_names(core, device)),
    ("definePixelSizeConfig", 2): (1, lambda core, device: _get_prop_names(core, device)),  # noqa
    ("deleteConfig", 3): (2, lambda core, device: _get_prop_names(core, device)),
    ("getAllowedPropertyValues", 1): (0, lambda core, device: _get_prop_names(core, device)),  # noqa
    ("getProperty", 1): (0, lambda core, device: _get_prop_names(core, device)),
    ("getPropertyFromCache", 1): (0, lambda core, device: _get_prop_names(core, device)),  # noqa
    ("getPropertyLowerLimit", 1): (0, lambda core, device: _get_prop_names(core, device)),  # noqa
    ("getPropertySequenceMaxLength", 1): (0, lambda core, device: _get_prop_names(core, device)),  # noqa
    ("getPropertyType", 1): (0, lambda core, device: _get_prop_names(core, device)),
    ("getPropertyUpperLimit", 1): (0, lambda core, device: _get_prop_names(core, device)),  # noqa
    ("hasProperty", 1): (0, lambda core, device: _get_prop_names(core, device)),
    ("hasPropertyLimits", 1): (0, lambda core, device: _get_prop_names(core, device)),
    ("isPropertyPreInit", 1): (0, lambda core, device: _get_prop_names(core, device)),
    ("isPropertyReadOnly", 1): (0, lambda core, device: _get_prop_names(core, device)),
    ("isPropertySequenceable", 1): (0, lambda core, device: _get_prop_names(core, device)),  # noqa
    ("loadPropertySequence", 1): (0, lambda core, device: _get_prop_names(core, device)),  # noqa
    ("setProperty", 1): (0, lambda core, device: _get_prop_names(core, device)),
    ("startPropertySequence", 1): (0, lambda core, device: _get_prop_names(core, device)),  # noqa
    ("stopPropertySequence", 1): (0, lambda core, device: _get_prop_names(core, device)),  # noqa
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
        return _null(ctx)  # pragma: no cover
    ns = ip.user_ns  # live user namespace

    # e.g.: 'core.setCameraDevice('
    src_to_cursor = ctx.full_text[: ctx.cursor_position]

    # Extract the object expression and the *real* attribute name syntactically.
    if not (m := OBJ_METHOD_RE.search(src_to_cursor)):
        return _null(ctx)

    # e.g. ('core', 'setCameraDevice')
    var_expr, method_name = m.group("obj"), m.group("attr")
    try:
        obj = eval(var_expr, ns)
    except Exception:
        return _null(ctx)

    if not isinstance(obj, CMMCorePlus):
        return _null(ctx)

    # ── 1. Use Jedi to understand where we are ────────────────────────────────
    arg_index = _get_argument_index(src_to_cursor, ns)

    key = (method_name, arg_index)
    if (dev_getter := DEVICE_COMPLETERS.get(key)) and (completions := dev_getter(obj)):
        # If we have a specific suggestion for this method and arg_index, use it.
        return {"completions": completions, "suppress": True}

    if info := PROP_COMPLETERS.get(key):
        dev_idx, getter = info
        if dev_label := _get_argument(src_to_cursor, dev_idx):
            if completions := getter(obj, dev_label):
                return {"completions": completions, "suppress": True}

    return _null(ctx)


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
