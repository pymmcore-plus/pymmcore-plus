from __future__ import annotations

import gc
import inspect
import time
import types
import weakref
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from pymmcore_plus import CMMCorePlus
from pymmcore_plus._accumulator import DeviceAccumulator
from pymmcore_plus.core import _mmcore_plus


# hard to do this with a pytest fixture, because it also holds a reference.
@contextmanager
def clean_core() -> Iterator[CMMCorePlus]:
    """Create a clean CMMCorePlus instance and ensure it is properly cleaned on exit."""
    core = CMMCorePlus()
    core_ref = weakref.ref(core)

    class _Proxy:
        def __getattribute__(self, name: str) -> Any:
            return getattr(core, name)  # noqa

    yield _Proxy()  # type: ignore[misc]

    if _mmcore_plus._instance == core:
        _mmcore_plus._instance = None

    del core
    for _i in range(10):
        if gc.collect() == 0:
            break
        time.sleep(0.1)  # wait for the GC to settle

    if core_ref() is not None:
        lines = show_referrers(core_ref())
        raise AssertionError(
            "CMMCorePlus instance should be cleaned up, but has referrers:\n"
            + "\n".join(lines)
        )


def test_core_cleanup() -> None:
    with clean_core() as core:
        core.loadSystemConfiguration()


def test_device_object_refs() -> None:
    with clean_core() as core:
        core.loadSystemConfiguration()
        _obj = core.getDeviceObject("Camera")


def test_dev_accumulator() -> None:
    with clean_core() as core:
        core.loadSystemConfiguration()
        _dev = DeviceAccumulator.get_cached("XY", core)  # type: ignore
        assert _dev in DeviceAccumulator._CACHE.values()
    # assert _dev not in DeviceAccumulator._CACHE.values()  # not working yet


# ------------------------------- HELPERS -------------------------------


def _describe(obj: Any) -> str:
    """Return a one-liner describing *obj*."""
    # Built-in simple types ──────────────────────────────────────────────────
    if obj is None or isinstance(obj, (int, float, str, bytes, bool)):
        return repr(obj)

    # Functions / methods / code objects ─────────────────────────────────────
    if isinstance(obj, (types.FunctionType, types.MethodType)):
        mod = obj.__module__ or "?"
        qualname = getattr(obj, "__qualname__", obj.__name__)
        fn = inspect.getsourcefile(obj) or "built-in"
        return f"<function {mod}.{qualname} @ {fn}>"

    if isinstance(obj, types.CodeType):
        return f"<code {obj.co_name} @ {obj.co_filename}:{obj.co_firstlineno}>"

    # Frames ─────────────────────────────────────────────────────────────────
    if isinstance(obj, types.FrameType):
        code = obj.f_code
        return f"<frame {code.co_name} @ {code.co_filename}:{obj.f_lineno}>"

    # Modules ────────────────────────────────────────────────────────────────
    if isinstance(obj, types.ModuleType):
        return f"<module {obj.__name__} @ {getattr(obj, '__file__', 'built-in')}>"

    # Classes and instances ──────────────────────────────────────────────────
    if inspect.isclass(obj):
        return f"<class {obj.__module__}.{obj.__qualname__}>"

    # Most user objects arrive here
    cls = obj.__class__
    return f"<{cls.__module__}.{cls.__qualname__} id={id(obj):#x}>"


def _iter_children(container: Any) -> Iterable[tuple[str, Any]]:
    """Yield (how, child) pairs for every element that *container* owns."""
    # Dict-like containers
    if isinstance(container, Mapping):
        for k, v in container.items():
            yield f"[{k!r}]", v
    # Sequence types (but not str / bytes / bytearray)
    elif isinstance(container, Sequence) and not isinstance(
        container, (str, bytes, bytearray)
    ):
        for i, v in enumerate(container):
            yield f"[{i}]", v
    # Attribute dictionaries of *most* user objects
    elif hasattr(container, "__dict__"):
        for k, v in vars(container).items():
            yield f".{k}", v
    # Slots
    if hasattr(container, "__slots__"):
        for name in container.__slots__:  # type: ignore[attr-defined]
            try:
                v = getattr(container, name)
            except AttributeError:
                continue
            yield f".{name}", v


def _walk(
    root: Any,
    max_depth: int,
    *,
    seen: set[int],
    prefix: str = "",
) -> Iterable[str]:
    """Recursive DFS walking *referrer* tree with cycle detection."""
    if max_depth < 0:
        return
    for ref in gc.get_referrers(root):
        ref_id = id(ref)
        if ref_id in seen or ref is globals() or ref is locals():
            continue  # avoid loops and GC internals
        seen.add(ref_id)

        descr = _describe(ref)
        yield f"{prefix}└─ {descr}"
        # Show *how* root is stored inside *ref* (when we can work it out)
        try:
            for how, child in _iter_children(ref):
                if child is root:
                    yield f"{prefix}    ↳ via {how}"
        except Exception:
            pass  # best-effort; ignore exotic containers

        _walk(ref, max_depth - 1, seen=seen, prefix=prefix + "    ")

        # Extra blank line between top-level branches for readability
        if prefix == "":
            yield ""


def show_referrers(obj: Any, *, max_depth: int = 3) -> list[str]:
    """
    Print a tree of *strong* referrers that keep *obj* alive.

    Parameters
    ----------
    obj:
        The object you expect to be collectible.
    max_depth:
        Follow referrer chains up to this depth (default 3).  Increase if you
        need to chase deeply nested structures, but be aware the graph may
        explode.

    Notes
    -----
    • `gc.collect()` is **not** called automatically.  Collect first if you
      want to rule out garbage-cycle leftovers.
    • Allocation site information isn't recorded by CPython for arbitrary
      objects.  We therefore rely on what *is* available:

        - module/file for functions and modules
        - filename + line for frames and code objects
        - `__module__` + class name for instances

      For deeper insight you can enable `tracemalloc` **before** the suspect
      objects are created, then combine its snapshot with the IDs printed
      here.
    """
    if max_depth < 1:
        raise ValueError("max_depth must be ≥ 1")
    lines = [f"Reference tree for {_describe(obj)}"]
    lines.extend(_walk(obj, max_depth, seen={id(obj)}))
    return lines
