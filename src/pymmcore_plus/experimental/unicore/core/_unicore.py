from __future__ import annotations

import importlib
import weakref
from contextlib import suppress
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from pymmcore_plus import _pymmcore
from pymmcore_plus.core import CMMCorePlus
from pymmcore_plus.experimental.unicore.devices._device_base import Device
from pymmcore_plus.experimental.unicore.devices._hub import HubDevice
from pymmcore_plus.experimental.unicore.devices._properties import to_cpp_string
from pymmcore_plus.experimental.unicore.devices._slm import SLMDevice

from ._adapter_discovery import create_adapter_from_module, discover_entry_points
from ._config import load_system_configuration, save_system_configuration

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from types import ModuleType

    from pymmcore import AdapterName, DeviceLabel, DeviceName

    from pymmcore_plus.core import DeviceType


class UniMMCore(CMMCorePlus):
    """Unified Core object supporting both C++ and Python devices.

    Python devices are loaded via the C++ bridge (loadPyDevice), which registers
    them as real devices in CMMCore's registry. Most CMMCore methods work
    natively without interception.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if not _pymmcore.BACKEND == "pymmcore-nano":
            raise RuntimeError(
                "UniMMCore requires the 'pymmcore-nano' backend. "
                f"Current backend: {_pymmcore.BACKEND}"
            )

        # Track which labels are Python devices and keep refs to Device objects
        self._pydevices: dict[str, Device] = {}
        # Labels of devices loaded with loadPyDevice() (their one-off bridge
        # adapter is named after neither their module nor the device class).
        self._direct_pydevices: set[str] = set()
        # Devices instantiated by the bridge (from a registered Python adapter
        # or a hub's peripheral class) that have not been initialized yet, so
        # are not known by label.
        self._pending_pydevices: list[Device] = []
        # Peripheral tracking for loaded Python hubs: {hub label: tracker}
        self._hub_trackers: dict[str, _HubPeripheralTracker] = {}

        # Python adapter discovery: {adapter_name: module_path}
        self._py_adapter_registry: dict[str, str] = discover_entry_points()
        self._registered_py_adapters: set[str] = set()

        super().__init__(*args, **kwargs)

        weakref.finalize(self, UniMMCore._cleanup_python_state, self._pydevices)

    @staticmethod
    def _cleanup_python_state(pydevices: dict[str, Device]) -> None:
        pydevices.clear()

    # -----------------------------------------------------------------------
    # Device loading / unloading
    # -----------------------------------------------------------------------

    def loadDevice(
        self, label: str, moduleName: AdapterName | str, deviceName: DeviceName | str
    ) -> None:
        """Load a device from a C++ plugin library or Python module."""
        # Lazily register any discovered Python adapter before the C++ attempt
        self._ensure_py_adapter_loaded(moduleName)

        self._pending_pydevices.clear()
        try:
            CMMCorePlus.loadDevice(self, label, moduleName, deviceName)
        except RuntimeError as e:
            if moduleName not in super().getDeviceAdapterNames():
                # a peripheral of a loaded Python hub, reported by its
                # detect_installed_devices()? (the hub's library is its module)
                if self._load_hub_peripheral(label, moduleName, deviceName):
                    return
                pydev = self._get_py_device_instance(moduleName, deviceName)
                self.loadPyDevice(label, pydev)
                return
            if exc := self._load_error_with_info(label, moduleName, deviceName, str(e)):
                raise exc from e
        else:
            self._adopt_bridge_created(label, deviceName)

    def _load_hub_peripheral(self, label: str, module: str, name: str) -> bool:
        """Load `name` from a loaded Python hub whose library is `module`."""
        for hub_label, tracker in list(self._hub_trackers.items()):
            if self.getDeviceLibrary(hub_label) != module:
                continue
            try:
                CMMCorePlus.loadDevice(self, label, tracker.library, name)
            except RuntimeError:
                continue
            self._adopt_bridge_created(label, name)
            return True
        return False

    def _adopt_bridge_created(self, label: str, device_name: str) -> None:
        """Track the Device the bridge created (if any) for a loaded label."""
        pending, self._pending_pydevices = self._pending_pydevices, []
        # a peripheral *instance* reported by a hub's detect_installed_devices()
        library = super().getDeviceLibrary(label)
        for tracker in self._hub_trackers.values():
            if tracker.library == library and device_name in tracker.instances:
                self._adopt_py_device(label, tracker.instances[device_name])
                return
        # A device instantiated by the bridge for this label (none for C++
        # devices): a registered adapter's class, or a hub's peripheral class.
        # The bridge instantiates it last; the hub's peripheral detection that
        # may precede it only creates prototypes (for getInstalledDevices()).
        if pending:
            self._adopt_py_device(label, pending[-1])

    def _adopt_py_device(self, label: str, device: Device) -> None:
        """Track a Device instance the bridge created for `label`."""
        device._label_ = label
        self._pydevices[label] = device
        # the bridge may hand the device a different label (e.g. hub peripherals
        # created for getInstalledDevices() are never loaded under one).
        device._on_bridge_label_ = self._on_bridge_label
        if isinstance(device, HubDevice):
            self._track_hub(label, device)

    def _track_hub(self, label: str, hub: HubDevice) -> None:
        """Make the hub's detect_installed_devices() report its peripherals here.

        The bridge loads the peripherals a hub reports: instances as they are,
        classes by instantiating them. The tracker records the instances and
        wraps the classes, so that both end up in `_pydevices` when loaded.
        """
        tracker = _HubPeripheralTracker(self, hub, super().getDeviceLibrary(label))
        # (an instance attribute, so that the bridge finds it on the hub object)
        hub.__dict__["detect_installed_devices"] = tracker
        self._hub_trackers[label] = tracker

    def _on_bridge_label(self, device: Device) -> None:
        if (label := device.get_label()) and self._pydevices.get(label) is not device:
            self._pydevices[label] = device

    def _get_py_device_instance(self, module_name: str, cls_name: str) -> Device:
        """Import and instantiate a python device from `module_name.cls_name`."""
        try:
            module = __import__(module_name, fromlist=[cls_name])
        except ImportError as e:
            raise type(e)(
                f"{module_name!r} is not a known Micro-manager DeviceAdapter, or "
                "an importable python module "
            ) from e
        try:
            cls = getattr(module, cls_name)
        except AttributeError as e:
            raise AttributeError(
                f"Could not find class {cls_name!r} in python module {module_name!r}"
            ) from e
        if isinstance(cls, type) and issubclass(cls, Device):
            return cls()
        raise TypeError(f"{cls_name} is not a subclass of Device")

    def loadPyDevice(self, label: str, device: Device) -> None:
        """Load a unicore.Device as a Python device via the C++ bridge.

        The device is registered in CMMCore as a real device. All property
        access, camera acquisition, etc. work natively through CMMCore.
        """
        if label in self.getLoadedDevices():
            raise ValueError(f"The specified device label {label!r} is already in use")

        device._label_ = label

        # Register with C++ bridge — the bridge will call device.initialize()
        # later when initializeDevice() is called.
        super().loadPyDevice(label, device, device.type())  # type: ignore[misc]
        self._pydevices[label] = device
        self._direct_pydevices.add(label)
        if isinstance(device, HubDevice):
            self._track_hub(label, device)

    load_py_device = loadPyDevice

    # TODO: this could be upstreamed to nano
    def isPyDevice(self, label: DeviceLabel | str) -> bool:
        """Returns True if the label corresponds to a Python device."""
        return label in self._pydevices

    # -----------------------------------------------------------------------
    # Python adapter discovery and registration
    # -----------------------------------------------------------------------

    def register_py_adapter(
        self, adapter_name: str, module_or_path: str | ModuleType
    ) -> None:
        """Register a Python module as a device adapter.

        After registration, all Device subclasses in the module are available
        through the standard CMMCore API (getAvailableDevices, loadDevice, etc.).
        """
        if isinstance(module_or_path, str):
            module = importlib.import_module(module_or_path)
        else:
            module = module_or_path
        adapter = create_adapter_from_module(
            module, on_create=self._pending_pydevices.append
        )
        super().loadPyDeviceAdapter(adapter_name, adapter)  # type: ignore[misc]
        self._registered_py_adapters.add(adapter_name)

    def _ensure_py_adapter_loaded(self, adapter_name: str) -> None:
        """Lazily register a Python adapter if it was discovered via entry points."""
        if adapter_name in self._registered_py_adapters:
            return
        if adapter_name not in self._py_adapter_registry:
            return
        module_path = self._py_adapter_registry.pop(adapter_name)
        self.register_py_adapter(adapter_name, module_path)

    def getDeviceAdapterNames(self) -> tuple[AdapterName, ...]:
        """Return all adapter names, including discovered Python adapters."""
        names = list(super().getDeviceAdapterNames())
        seen: set[str] = set(names)
        for name in chain(self._py_adapter_registry, self._registered_py_adapters):
            if name not in seen:
                seen.add(name)
                names.append(cast("AdapterName", name))
        return tuple(names)

    def getAvailableDevices(self, library: str) -> tuple[DeviceName, ...]:
        self._ensure_py_adapter_loaded(library)
        return super().getAvailableDevices(library)

    def getAvailableDeviceDescriptions(self, library: str) -> tuple[str, ...]:
        self._ensure_py_adapter_loaded(library)
        return super().getAvailableDeviceDescriptions(library)

    def getAvailableDeviceTypes(self, library: str) -> tuple[int, ...]:
        self._ensure_py_adapter_loaded(library)
        return super().getAvailableDeviceTypes(library)

    # -- Device info overrides (C++ returns bridge adapter info, we want device info) --

    def getDeviceLibrary(self, label: DeviceLabel | str) -> AdapterName:
        lib = super().getDeviceLibrary(label)
        # A device loaded with loadPyDevice() sits behind a one-off bridge adapter
        # ("_PyBridge_N"); report its module instead. A peripheral loaded from
        # such a hub reports the hub's library. Devices from a registered Python
        # adapter report that adapter's name, like C++ devices.
        if label in self._pydevices and lib.startswith("_PyBridge_"):
            if label not in self._direct_pydevices:
                for hub_label, tracker in self._hub_trackers.items():
                    if tracker.library == lib and hub_label != label:
                        return self.getDeviceLibrary(hub_label)
            return cast("AdapterName", self._pydevices[label].__module__)
        return lib

    def getDeviceName(self, label: DeviceLabel | str) -> DeviceName:
        # loadPyDevice() registers the device under its label; devices created
        # by the bridge (adapter classes, hub peripherals) have a real name.
        if label not in self._direct_pydevices:
            return super().getDeviceName(label)
        return cast("DeviceName", self._pydevices[label].name())

    def getDeviceDescription(self, label: DeviceLabel | str) -> str:
        if label not in self._pydevices:
            return super().getDeviceDescription(label)
        return self._pydevices[label].description()

    # -- setProperty: enforce Python-side validation before C++ --

    def setProperty(
        self, label: str, propName: str, propValue: bool | float | int | str
    ) -> None:
        if label in self._pydevices:
            # Validate and set via Python property controller rather than going
            # through CMMCore's C++ property system. This is desirable because
            # MM::FloatProperty::Set(const char*) uses atof() to parse strings,
            # which silently converts invalid input to 0.0 (e.g. atof("bad") == 0).
            # By the time the bridge's AfterSet action functor fires, the property
            # already holds 0.0 — the original bad value is gone and unrecoverable.
            # Validating here catches type errors, limit violations, and disallowed
            # values with clear Python exceptions before C++ ever sees the value.
            # Properties provided by the C++ bridge itself (e.g. a State device's
            # Label) have no Python controller, and are validated by C++.
            dev = self._pydevices[label]
            if dev.has_property(propName):
                propValue = _prepare_property_value_for_cpp(dev, propName, propValue)
        super().setProperty(label, propName, propValue)

    # -- Config groups: ensure typed values are converted to strings --

    def defineConfig(
        self,
        groupName: str,
        configName: str,
        deviceLabel: str | None = None,
        propName: str | None = None,
        value: Any = None,
    ) -> None:
        if deviceLabel is not None and propName is not None and value is not None:
            super().defineConfig(
                groupName, configName, deviceLabel, propName, to_cpp_string(value)
            )
        else:
            super().defineConfig(groupName, configName)

    # -- getCurrentConfig: C++ string comparison fails for numeric format diffs --

    def getCurrentConfig(self, groupName: str) -> str:  # type: ignore[override]
        if result := super().getCurrentConfig(groupName):
            return result
        return self._find_matching_preset(groupName)

    def getCurrentConfigFromCache(self, groupName: str) -> str:  # type: ignore[override]
        if result := super().getCurrentConfigFromCache(groupName):
            return result
        return self._find_matching_preset(groupName)

    def _find_matching_preset(self, groupName: str) -> str:
        """Check presets with numeric-aware comparison."""
        for preset_name in self.getAvailableConfigs(groupName):
            cfg = super().getConfigData(groupName, preset_name, native=True)
            all_match = True
            for i in range(cfg.size()):
                s = cfg.getSetting(i)
                dev = s.getDeviceLabel()
                prop = s.getPropertyName()
                stored = s.getPropertyValue()
                try:
                    current = super().getProperty(dev, prop)
                except Exception:
                    all_match = False
                    break
                if not _values_match(current, stored):
                    all_match = False
                    break
            if all_match:
                return preset_name
        return ""

    def unloadDevice(self, label: DeviceLabel | str) -> None:
        super().unloadDevice(label)
        self._prune_py_devices()

    def _prune_py_devices(self) -> None:
        """Forget the Python devices that are no longer loaded."""
        loaded = set(super().getLoadedDevices())
        for label in list(self._pydevices):
            if label not in loaded:
                self._pydevices.pop(label, None)
                self._direct_pydevices.discard(label)
                self._hub_trackers.pop(label, None)

    def _stop_running_sequence(self) -> None:
        # CMMCore refuses to drop the camera role while it is acquiring
        with suppress(Exception):
            if self.isSequenceRunning():
                self.stopSequenceAcquisition()

    def unloadAllDevices(self) -> None:
        self._stop_running_sequence()
        try:
            super().unloadAllDevices()
        finally:
            self._prune_py_devices()

    def reset(self) -> None:
        self._stop_running_sequence()
        try:
            super().reset()
        finally:
            self._prune_py_devices()

    # -----------------------------------------------------------------------
    # System configuration files
    # -----------------------------------------------------------------------

    def loadSystemConfiguration(
        self, fileName: str | Path = "MMConfig_demo.cfg"
    ) -> None:
        """Load a system config file conforming to the MM `.cfg` format.

        Supports both C++ and Python devices. Lines prefixed with `#py ` are
        processed as Python device commands but ignored by upstream C++/pymmcore.
        """
        fpath = Path(fileName).expanduser()
        if not fpath.exists() and not fpath.is_absolute() and self._mm_path:
            fpath = Path(self._mm_path) / fileName
        if not fpath.exists():
            raise FileNotFoundError(f"Path does not exist: {fpath}")

        cfg_path = str(fpath.resolve())
        try:
            load_system_configuration(self, cfg_path)
        except Exception:
            with suppress(Exception):
                self.unloadAllDevices()
            raise

        self._last_sys_config = cfg_path
        self.events.systemConfigurationLoaded.emit()

    def saveSystemConfiguration(
        self, filename: str | Path, *, prefix_py_devices: bool = True
    ) -> None:
        """Save the current system configuration to a text file."""
        save_system_configuration(self, filename, prefix_py_devices=prefix_py_devices)

    # -----------------------------------------------------------------------
    # Thin overrides for type conversion (C++ expects strings)
    # -----------------------------------------------------------------------

    def loadPropertySequence(
        self,
        label: DeviceLabel | str,
        propName: str,
        eventSequence: Sequence[Any],
    ) -> None:
        # C++ expects Sequence[str]
        super().loadPropertySequence(
            label, propName, [to_cpp_string(v) for v in eventSequence]
        )

    # -- SLM overrides --

    def getSLMImage(self, slmLabel: DeviceLabel | str) -> Any:
        """Get the current image from a Python SLM device."""
        if slmLabel not in self._pydevices:
            raise NotImplementedError(
                "getSLMImage is not implemented for C++ SLM devices."
            )
        dev = self._pydevices[slmLabel]
        if isinstance(dev, SLMDevice):
            return dev.get_image()
        raise RuntimeError(f"Device {slmLabel!r} is not an SLM device")


class _HubPeripheralTracker:
    """Wraps a Python hub's `detect_installed_devices()` for a UniMMCore.

    Instances reported by the hub are recorded by name, so the core can track
    them once loaded. Classes are replaced by factories (which the bridge calls
    on each load, like a class) that hand every new instance to the core
    (`_pending_pydevices`), as a registered adapter does.
    """

    def __init__(self, core: UniMMCore, hub: HubDevice, library: str) -> None:
        self._core = weakref.ref(core)
        self._hub = hub
        self._detect = type(hub).detect_installed_devices
        self.library = library  # the bridge adapter the hub was loaded from
        self.instances: dict[str, Device] = {}
        self._factories: dict[type[Device], Callable[[], Device]] = {}

    def __call__(self) -> list[tuple[str, Any, DeviceType]]:
        out: list[tuple[str, Any, DeviceType]] = []
        items: Sequence[tuple[str, Any, DeviceType]] = self._detect(self._hub)
        for name, obj, dev_type in items:
            if isinstance(obj, type):
                obj = self._tracking_factory(obj)
            else:
                self.instances[name] = obj
            out.append((name, obj, dev_type))
        return out

    def _tracking_factory(self, cls: type[Device]) -> Callable[[], Device]:
        if cls not in self._factories:
            core_ref = self._core

            def factory() -> Device:
                dev = cls()
                if (core := core_ref()) is not None:
                    core._pending_pydevices.append(dev)  # noqa: SLF001
                return dev

            self._factories[cls] = factory
        return self._factories[cls]


def _values_match(current: Any, expected: Any) -> bool:
    """Compare property values with numeric-aware comparison."""
    if current == expected:
        return True
    try:
        return float(current) == float(expected)
    except (ValueError, TypeError):
        return str(current) == str(expected)


def _prepare_property_value_for_cpp(dev: Device, propName: str, propValue: Any) -> str:
    ctrl = dev._get_prop_or_raise(propName)  # noqa: SLF001
    if ctrl.is_read_only:
        raise ValueError(f"Property {propName!r} is read-only.")
    return to_cpp_string(ctrl.validate(propValue))
