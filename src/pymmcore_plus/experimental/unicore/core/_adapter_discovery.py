"""Discovery and registration of Python device adapter modules."""

from __future__ import annotations

import importlib
import importlib.metadata
import inspect
from typing import TYPE_CHECKING

from pymmcore_plus.experimental.unicore.devices._device_base import Device

if TYPE_CHECKING:
    from types import ModuleType

    from pymmcore_nano import DeviceAdapter

ENTRY_POINT_GROUP = "pymmcore-plus.adapters"


def discover_entry_points() -> dict[str, str]:
    """Return {adapter_name: module_path} from installed entry points."""
    eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    return {ep.name: ep.value for ep in eps}


def scan_module_for_devices(module: ModuleType) -> list[type[Device]]:
    """Find concrete Device subclasses in a module.

    If the module defines ``__pymmcore_devices__``, that list is used directly.
    Otherwise, the module namespace is scanned for non-abstract Device subclasses
    whose ``__module__`` matches.
    """
    if hasattr(module, "__pymmcore_devices__"):
        return list(module.__pymmcore_devices__)

    pkg = module.__package__ or module.__name__.split(".")[0]
    results: list[type[Device]] = []
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if (
            issubclass(obj, Device)
            and obj is not Device
            and not inspect.isabstract(obj)
            and obj.__module__.startswith(pkg)
        ):
            results.append(obj)
    return results


def create_adapter_from_module(module: ModuleType) -> DeviceAdapter:
    """Create a DeviceAdapter from all Device subclasses in a module."""
    from pymmcore_nano import DeviceAdapter

    device_classes = scan_module_for_devices(module)
    adapter = DeviceAdapter()
    for cls in device_classes:
        adapter.add_device_class(cls.name(), cls, cls.type(), cls.__doc__ or "")
    return adapter
