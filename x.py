# ~/.ipython/profile_default/startup/50-cmmcoreplus-completion.py
from __future__ import annotations

import re

import jedi
from IPython import get_ipython
from IPython.core.completer import (
    CompletionContext,
    SimpleCompletion,
    context_matcher,
)

# >>> replace these with the real imports you use
from pymmcore_plus import CMMCorePlus, DeviceType


def _null(ctx: CompletionContext) -> dict:
    return {"completions": [], "matched_fragment": "", "suppress": False}


@context_matcher()  # <-- official hook (IPython ≥ 6.0)
def cmmcoreplus_matcher(ctx: CompletionContext) -> dict:
    """
    Offer string completions for CMMCorePlus calls such as.

        core.setCameraDevice(<TAB>)
        core.setProperty("CAM", <TAB>)
    """
    if not (ip := get_ipython()):
        return _null(ctx)
    ns = ip.user_ns  # live user namespace

    # ── 1. Use Jedi to understand where we are ────────────────────────────────
    src_to_cursor = ctx.full_text[: ctx.cursor_position]
    script = jedi.Interpreter(src_to_cursor, [ns])
    sigs = script.get_signatures()

    if not sigs:  # not inside a call
        return _null(ctx)

    sig = sigs[-1]
    arg_index = sig.index  # 0‑based argument index

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

    # Only proceed for methods we care about

    completions: list[SimpleCompletion] = []

    if method_name == "setCameraDevice" and arg_index == 0:
        cams = obj.getLoadedDevicesOfType(DeviceType.Camera)
        completions = [SimpleCompletion(f'"{cam}"') for cam in cams] + [
            SimpleCompletion("''")
        ]
        return {"completions": completions, "suppress": True}

    if method_name == "getState" and arg_index == 0:
        states = obj.getLoadedDevicesOfType(DeviceType.State)
        states = [SimpleCompletion(f'"{state}"') for state in states]
        return {"completions": states, "suppress": True}

    elif method_name == "setProperty":
        # naïve parsing of args already typed inside the parens
        arg_list = [
            p.strip().strip("\"'")
            for p in src_to_cursor[src_to_cursor.rfind("(") + 1 :].split(",")
        ]

        if arg_index == 0:  # want a device label
            completions = [SimpleCompletion(lbl) for lbl in obj.getLoadedDevices()]

        elif arg_index == 1 and arg_list:
            label = arg_list[0]
            if label in obj.getLoadedDevices():
                props = obj.getDevicePropertyNames(label)
                completions = [SimpleCompletion(p) for p in props]

        elif arg_index == 2 and len(arg_list) >= 2:
            label, prop = arg_list[0], arg_list[1]
            if label in obj.getLoadedDevices() and obj.hasProperty(label, prop):
                vals = obj.getAllowedPropertyValues(label, prop)
                completions = [SimpleCompletion(v) for v in vals]

    if completions:
        return {"completions": completions, "suppress": True}

    return _null(ctx)


# ── 4. Register the matcher with IPython at startup ─────────────────────────
get_ipython().Completer.custom_matchers.append(cmmcoreplus_matcher)

core = CMMCorePlus()  # for testing in the IPython shell
core.loadSystemConfiguration()  # load the default config
