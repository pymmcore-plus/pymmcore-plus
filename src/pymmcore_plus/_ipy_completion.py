from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Callable, cast

import jedi
from IPython import get_ipython  # pyright: ignore
from IPython.core.completer import (
    CompletionContext,
    IPCompleter,
    SimpleCompletion,
    context_matcher,
)

from pymmcore_plus import CMMCorePlus, DeviceType

CoreCompleter = Callable[[CMMCorePlus], Sequence[SimpleCompletion]]


def _null(ctx: CompletionContext) -> dict:
    return {"completions": [], "matched_fragment": "", "suppress": False}


def _dev_labels(
    core: CMMCorePlus, *dev_types: DeviceType, with_null: bool = False
) -> Sequence[SimpleCompletion]:
    if not dev_types:
        labels = list(core.getLoadedDevices())
    else:
        labels = [
            d for dev_type in dev_types for d in core.getLoadedDevicesOfType(dev_type)
        ]
    completions = [SimpleCompletion(f'"{lbl}"') for lbl in labels]
    if with_null:
        completions.append(SimpleCompletion("''"))
    return completions


# fmt: off
# map of (method_name, arg_index) -> function that returns possible completions
SUGGESTION_MAP: dict[tuple[str, int], CoreCompleter] = {
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
}
# fmt: on


@context_matcher()  # type: ignore[misc]
def cmmcoreplus_matcher(ctx: CompletionContext) -> dict:
    """
    Offer string completions for CMMCorePlus calls such as.

        core.setCameraDevice(<TAB>)
        core.setProperty("CAM", <TAB>)
    """
    if not (ip := get_ipython()):
        return _null(ctx)
    ns = ip.user_ns  # live user namespace

    src_to_cursor = ctx.full_text[: ctx.cursor_position]

    # Extract the object expression and the *real* attribute name syntactically.
    m = re.search(r"([A-Za-z_][\w\.]*)\.(\w+)\s*\(", src_to_cursor)
    if not m:
        return _null(ctx)
    var_expr, method_name = m.groups()

    try:
        obj = eval(var_expr, ns)
    except Exception:
        return _null(ctx)

    if not isinstance(obj, CMMCorePlus):
        return _null(ctx)

    # ── 1. Use Jedi to understand where we are ────────────────────────────────
    script = jedi.Interpreter(src_to_cursor, [ns])
    sigs = script.get_signatures()

    if not sigs:  # not inside a call
        return _null(ctx)

    sig = sigs[-1]
    arg_index = sig.index  # 0-based argument index

    if (method_name, arg_index) in SUGGESTION_MAP:
        # If we have a specific suggestion for this method and arg_index, use it.
        completions = SUGGESTION_MAP[(method_name, arg_index)](obj)
        return {"completions": completions, "suppress": True}

    # elif method_name == "setProperty":
    #     # naive parsing of args already typed inside the parens
    #     arg_list = [
    #         p.strip().strip("\"'")
    #         for p in src_to_cursor[src_to_cursor.rfind("(") + 1 :].split(",")
    #     ]

    #     if arg_index == 0:  # want a device label
    #         completions = [SimpleCompletion(lbl) for lbl in obj.getLoadedDevices()]

    #     elif arg_index == 1 and arg_list:
    #         label = arg_list[0]
    #         if label in obj.getLoadedDevices():
    #             props = obj.getDevicePropertyNames(label)
    #             completions = [SimpleCompletion(p) for p in props]

    #     elif arg_index == 2 and len(arg_list) >= 2:
    #         label, prop = arg_list[0], arg_list[1]
    #         if label in obj.getLoadedDevices() and obj.hasProperty(label, prop):
    #             vals = obj.getAllowedPropertyValues(label, prop)
    #             completions = [SimpleCompletion(v) for v in vals]

    return _null(ctx)


def install_pymmcore_ipy_completion() -> None:
    """Install the CMMCorePlus completion matcher in the current IPython session."""
    ip = get_ipython()
    if not ip:
        return
    completer = cast("IPCompleter", ip.Completer)
    if cmmcoreplus_matcher not in completer.custom_matchers:
        completer.custom_matchers.append(cmmcoreplus_matcher)


install_pymmcore_ipy_completion()
core = CMMCorePlus()
core.loadSystemConfiguration()
