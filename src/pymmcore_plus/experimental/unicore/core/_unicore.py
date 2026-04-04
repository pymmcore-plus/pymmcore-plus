from __future__ import annotations

import weakref
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from pymmcore_plus import _pymmcore
from pymmcore_plus.core import CMMCorePlus
from pymmcore_plus.experimental.unicore.devices._device_base import Device
from pymmcore_plus.experimental.unicore.devices._slm import SLMDevice

from ._config import load_system_configuration, save_system_configuration

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pymmcore import AdapterName, DeviceLabel, DeviceName


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
        try:
            CMMCorePlus.loadDevice(self, label, moduleName, deviceName)
        except RuntimeError as e:
            if moduleName not in super().getDeviceAdapterNames():
                pydev = self._get_py_device_instance(moduleName, deviceName)
                self.loadPyDevice(label, pydev)
                return
            if exc := self._load_error_with_info(label, moduleName, deviceName, str(e)):
                raise exc from e

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

    load_py_device = loadPyDevice

    # TODO: this could be upstreamed to nano
    def isPyDevice(self, label: DeviceLabel | str) -> bool:
        """Returns True if the label corresponds to a Python device."""
        return label in self._pydevices

    # -- Device info overrides (C++ returns bridge adapter info, we want device info) --

    def getDeviceLibrary(self, label: DeviceLabel | str) -> AdapterName:
        if label not in self._pydevices:
            return super().getDeviceLibrary(label)
        return cast("AdapterName", self._pydevices[label].__module__)

    def getDeviceName(self, label: DeviceLabel | str) -> DeviceName:
        if label not in self._pydevices:
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
            dev = self._pydevices[label]
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
                groupName, configName, deviceLabel, propName, str(value)
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
        self._pydevices.pop(label, None)

    def unloadAllDevices(self) -> None:
        with suppress(Exception):
            if self.isSequenceRunning():
                self.stopSequenceAcquisition()
        self._pydevices.clear()
        super().unloadAllDevices()

    def reset(self) -> None:
        self._pydevices.clear()
        super().reset()

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
        super().loadPropertySequence(label, propName, [str(v) for v in eventSequence])

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
    propValue = ctrl.validate(propValue)
    if isinstance(propValue, bool):
        propValue = int(propValue)  # MM properties expect bools as ints
    # For config properties (no fset), update last_value directly
    # since the C++ bridge setter may not fire for getter-less properties.
    if ctrl.fset is None:
        ctrl.property.last_value = propValue
    return str(propValue)
