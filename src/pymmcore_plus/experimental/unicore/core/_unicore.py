from __future__ import annotations

import time
import weakref
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np

import pymmcore_plus._pymmcore as pymmcore
from pymmcore_plus.core import CMMCorePlus, DeviceType
from pymmcore_plus.core import Keyword as KW
from pymmcore_plus.core._constants import DeviceInitializationState
from pymmcore_plus.experimental.unicore.devices._device_base import Device
from pymmcore_plus.experimental.unicore.devices._hub import HubDevice
from pymmcore_plus.experimental.unicore.devices._slm import SLMDevice
from pymmcore_plus.experimental.unicore.devices._stage import (
    StageDevice,
    XYStageDevice,
)

from ._config import load_system_configuration, save_system_configuration

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pymmcore import AdapterName, DeviceLabel, DeviceName


class _PyDeviceRegistry(dict):
    """Dict subclass with convenience methods for tracking Python devices."""

    def wait_for_device_type(self, dev_type: int, timeout_ms: float = 5000) -> None:
        """Wait for all Python devices of the given type to not be busy."""
        deadline = time.perf_counter() + timeout_ms / 1000
        for dev in self.values():
            if dev_type != DeviceType.Any and dev.type() != dev_type:
                continue
            while dev.busy():
                if time.perf_counter() > deadline:
                    raise TimeoutError(
                        f"Wait for device timed out after {timeout_ms} ms"
                    )
                time.sleep(0.01)


# Map Device._TYPE to pymmcore DeviceType for loadPyDevice
_DEVICE_TYPE_MAP: dict[DeviceType, int] = {
    DeviceType.Camera: DeviceType.Camera,
    DeviceType.ShutterDevice: DeviceType.ShutterDevice,
    DeviceType.Stage: DeviceType.Stage,
    DeviceType.XYStage: DeviceType.XYStage,
    DeviceType.State: DeviceType.State,
    DeviceType.SLM: DeviceType.SLM,
    DeviceType.Hub: DeviceType.Hub,
    DeviceType.GenericDevice: DeviceType.GenericDevice,
}


class UniMMCore(CMMCorePlus):
    """Unified Core object supporting both C++ and Python devices.

    Python devices are loaded via the C++ bridge (loadPyDevice), which registers
    them as real devices in CMMCore's registry. Most CMMCore methods work
    natively without interception.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Track which labels are Python devices and keep refs to Device objects
        self._pydevices: _PyDeviceRegistry = _PyDeviceRegistry()
        super().__init__(*args, **kwargs)

        weakref.finalize(
            self,
            UniMMCore._cleanup_python_state,
            self._pydevices,
        )

    @staticmethod
    def _cleanup_python_state(pydevices: dict[str, Device]) -> None:
        for dev in pydevices.values():
            with suppress(Exception):
                dev.shutdown()
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

        # Determine MM device type
        dev_type = _DEVICE_TYPE_MAP.get(device.type())
        if dev_type is None:
            raise TypeError(
                f"Unsupported device type {device.type()} for device {label!r}"
            )

        # Register with C++ bridge — the bridge will call device.initialize()
        # later when initializeDevice() is called.
        pymmcore.CMMCore.loadPyDevice(self, label, device, dev_type)
        self._pydevices[label] = device

    load_py_device = loadPyDevice

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

    def getDeviceInitializationState(self, label: str) -> Any:
        if label not in self._pydevices:
            return super().getDeviceInitializationState(label)
        state = self._pydevices[label]._initialized_
        if state is True:
            return DeviceInitializationState.InitializedSuccessfully
        if state is False:
            return DeviceInitializationState.Uninitialized
        return DeviceInitializationState.InitializationFailed

    def getDeviceType(self, label: str) -> DeviceType:
        if label not in self._pydevices:
            return super().getDeviceType(label)
        return self._pydevices[label].type()

    # -- setProperty: enforce Python-side validation before C++ --

    def setProperty(
        self, label: str, propName: str, propValue: bool | float | int | str
    ) -> None:
        if label in self._pydevices:
            dev = self._pydevices[label]
            # Validate and set via Python property controller
            dev.set_property_value(propName, propValue)
            # Notify CMMCore (updates state cache, posts async notifications)
            if dev._notify_ is not None:
                dev._notify_.on_property_changed(propName, str(propValue))
            return
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

    def getCurrentConfig(self, groupName: str) -> str:
        result = super().getCurrentConfig(groupName)
        if result:
            return result
        return self._find_matching_preset(groupName)

    def getCurrentConfigFromCache(self, groupName: str) -> str:
        result = super().getCurrentConfigFromCache(groupName)
        if result:
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

    # -- Hub peripherals --

    def getInstalledDevices(
        self, hubLabel: DeviceLabel | str
    ) -> tuple[DeviceName, ...]:
        if hubLabel not in self._pydevices:
            return tuple(super().getInstalledDevices(hubLabel))
        dev = self._pydevices[hubLabel]
        if isinstance(dev, HubDevice):
            peripherals = dev.get_installed_peripherals()
            return tuple(p[0] for p in peripherals if p[0])  # type: ignore[misc]
        return ()

    def getInstalledDeviceDescription(
        self, hubLabel: DeviceLabel | str, peripheralLabel: DeviceName | str
    ) -> str:
        if hubLabel not in self._pydevices:
            return super().getInstalledDeviceDescription(hubLabel, peripheralLabel)
        dev = self._pydevices[hubLabel]
        if isinstance(dev, HubDevice):
            for p in dev.get_installed_peripherals():
                if p[0] == peripheralLabel:
                    return p[1] or "N/A"
        raise RuntimeError(
            f"No peripheral with name {peripheralLabel!r} installed in hub {hubLabel!r}"
        )

    def getLoadedPeripheralDevices(
        self, hubLabel: DeviceLabel | str
    ) -> tuple[DeviceLabel, ...]:
        cpp_peripherals = super().getLoadedPeripheralDevices(hubLabel)
        # Also check Python devices for matching parent label
        py_peripherals = tuple(
            cast("DeviceLabel", label)
            for label, dev in self._pydevices.items()
            if dev.get_parent_label() == hubLabel
        )
        return tuple(cpp_peripherals) + py_peripherals

    def setParentLabel(
        self, deviceLabel: DeviceLabel | str, parentHubLabel: DeviceLabel | str
    ) -> None:
        if deviceLabel == KW.CoreDevice:
            return
        # Reject cross-language hub/peripheral relationships
        device_is_py = deviceLabel in self._pydevices
        parent_is_py = parentHubLabel in self._pydevices
        if parentHubLabel and device_is_py != parent_is_py:
            raise RuntimeError(
                "Cannot set cross-language parent/child relationship between "
                "C++ and Python devices"
            )
        if device_is_py:
            self._pydevices[deviceLabel].set_parent_label(parentHubLabel)
        else:
            super().setParentLabel(deviceLabel, parentHubLabel)

    def getParentLabel(self, peripheralLabel: DeviceLabel | str) -> str:
        if peripheralLabel not in self._pydevices:
            return super().getParentLabel(peripheralLabel)
        return self._pydevices[peripheralLabel].get_parent_label()

    def unloadDevice(self, label: DeviceLabel | str) -> None:
        self._pydevices.pop(label, None)
        super().unloadDevice(label)

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
    # Wait/busy methods — C++ handles bridge devices, but we also poll Python
    # -----------------------------------------------------------------------

    def waitForSystem(self) -> None:
        self.waitForDeviceType(DeviceType.AnyType)

    def systemBusy(self) -> bool:
        return self.deviceTypeBusy(DeviceType.AnyType)

    def waitForDeviceType(self, devType: int) -> None:
        super().waitForDeviceType(devType)
        self._pydevices.wait_for_device_type(devType, self.getTimeoutMs())

    def deviceTypeBusy(self, devType: int) -> bool:
        if super().deviceTypeBusy(devType):
            return True
        for dev in self._pydevices.values():
            if devType == DeviceType.Any or dev.type() == devType:
                if dev.busy():
                    return True
        return False

    # -----------------------------------------------------------------------
    # Property sequencing overrides (C++ bridge hardcodes sequencing to false)
    # These stay until pymmcore-nano adds native sequencing support.
    # -----------------------------------------------------------------------

    def isPropertySequenceable(self, label: DeviceLabel | str, propName: str) -> bool:
        if label not in self._pydevices:
            return super().isPropertySequenceable(label, propName)
        return self._pydevices[label].is_property_sequenceable(propName)

    def getPropertySequenceMaxLength(
        self, label: DeviceLabel | str, propName: str
    ) -> int:
        if label not in self._pydevices:
            return super().getPropertySequenceMaxLength(label, propName)
        return self._pydevices[label].get_property_info(propName).sequence_max_length

    def loadPropertySequence(
        self,
        label: DeviceLabel | str,
        propName: str,
        eventSequence: Sequence[Any],
    ) -> None:
        if label not in self._pydevices:
            return super().loadPropertySequence(label, propName, eventSequence)
        self._pydevices[label].load_property_sequence(propName, eventSequence)

    def startPropertySequence(self, label: DeviceLabel | str, propName: str) -> None:
        if label not in self._pydevices:
            return super().startPropertySequence(label, propName)
        self._pydevices[label].start_property_sequence(propName)

    def stopPropertySequence(self, label: DeviceLabel | str, propName: str) -> None:
        if label not in self._pydevices:
            return super().stopPropertySequence(label, propName)
        self._pydevices[label].stop_property_sequence(propName)

    # -- Exposure sequencing --

    def isExposureSequenceable(self, cameraLabel: DeviceLabel | str) -> bool:
        if cameraLabel not in self._pydevices:
            return super().isExposureSequenceable(cameraLabel)
        return self._pydevices[cameraLabel].is_property_sequenceable(KW.Exposure)

    def getExposureSequenceMaxLength(self, cameraLabel: DeviceLabel | str) -> int:
        if cameraLabel not in self._pydevices:
            return super().getExposureSequenceMaxLength(cameraLabel)
        return (
            self._pydevices[cameraLabel]
            .get_property_info(KW.Exposure)
            .sequence_max_length
        )

    def loadExposureSequence(
        self,
        cameraLabel: DeviceLabel | str,
        exposureSequence_ms: Sequence[float],
    ) -> None:
        if cameraLabel not in self._pydevices:
            return super().loadExposureSequence(cameraLabel, exposureSequence_ms)
        self._pydevices[cameraLabel].load_property_sequence(
            KW.Exposure, exposureSequence_ms
        )

    def startExposureSequence(self, cameraLabel: DeviceLabel | str) -> None:
        if cameraLabel not in self._pydevices:
            return super().startExposureSequence(cameraLabel)
        self._pydevices[cameraLabel].start_property_sequence(KW.Exposure)

    def stopExposureSequence(self, cameraLabel: DeviceLabel | str) -> None:
        if cameraLabel not in self._pydevices:
            return super().stopExposureSequence(cameraLabel)
        self._pydevices[cameraLabel].stop_property_sequence(KW.Exposure)

    # -- Stage sequencing --

    def isStageSequenceable(self, stageLabel: DeviceLabel | str) -> bool:
        if stageLabel not in self._pydevices:
            return super().isStageSequenceable(stageLabel)
        dev = self._pydevices[stageLabel]
        if isinstance(dev, StageDevice):
            return dev.is_sequenceable()
        return False

    def getStageSequenceMaxLength(self, stageLabel: DeviceLabel | str) -> int:
        if stageLabel not in self._pydevices:
            return super().getStageSequenceMaxLength(stageLabel)
        dev = self._pydevices[stageLabel]
        if isinstance(dev, StageDevice):
            return dev.get_sequence_max_length()
        return 0

    def loadStageSequence(
        self,
        stageLabel: DeviceLabel | str,
        positionSequence: Sequence[float],
    ) -> None:
        if stageLabel not in self._pydevices:
            return super().loadStageSequence(stageLabel, positionSequence)
        dev = self._pydevices[stageLabel]
        if isinstance(dev, StageDevice):
            dev.send_sequence(tuple(positionSequence))

    def startStageSequence(self, stageLabel: DeviceLabel | str) -> None:
        if stageLabel not in self._pydevices:
            return super().startStageSequence(stageLabel)
        dev = self._pydevices[stageLabel]
        if isinstance(dev, StageDevice):
            dev.start_sequence()

    def stopStageSequence(self, stageLabel: DeviceLabel | str) -> None:
        if stageLabel not in self._pydevices:
            return super().stopStageSequence(stageLabel)
        dev = self._pydevices[stageLabel]
        if isinstance(dev, StageDevice):
            dev.stop_sequence()

    # -- XYStage sequencing --

    def isXYStageSequenceable(self, xyStageLabel: DeviceLabel | str) -> bool:
        if xyStageLabel not in self._pydevices:
            return super().isXYStageSequenceable(xyStageLabel)
        dev = self._pydevices[xyStageLabel]
        if isinstance(dev, XYStageDevice):
            return dev.is_sequenceable()
        return False

    def getXYStageSequenceMaxLength(self, xyStageLabel: DeviceLabel | str) -> int:
        if xyStageLabel not in self._pydevices:
            return super().getXYStageSequenceMaxLength(xyStageLabel)
        dev = self._pydevices[xyStageLabel]
        if isinstance(dev, XYStageDevice):
            return dev.get_sequence_max_length()
        return 0

    def loadXYStageSequence(
        self,
        xyStageLabel: DeviceLabel | str,
        xSequence: Sequence[float],
        ySequence: Sequence[float],
        /,
    ) -> None:
        if xyStageLabel not in self._pydevices:
            return super().loadXYStageSequence(xyStageLabel, xSequence, ySequence)
        dev = self._pydevices[xyStageLabel]
        if isinstance(dev, XYStageDevice):
            if len(xSequence) != len(ySequence):
                raise ValueError("xSequence and ySequence must have the same length")
            seq = tuple(zip(xSequence, ySequence, strict=False))
            if len(seq) > dev.get_sequence_max_length():
                raise ValueError(
                    f"Sequence is too long. Max length is "
                    f"{dev.get_sequence_max_length()}"
                )
            dev.send_sequence(seq)

    def startXYStageSequence(self, xyStageLabel: DeviceLabel | str) -> None:
        if xyStageLabel not in self._pydevices:
            return super().startXYStageSequence(xyStageLabel)
        dev = self._pydevices[xyStageLabel]
        if isinstance(dev, XYStageDevice):
            dev.start_sequence()

    def stopXYStageSequence(self, xyStageLabel: DeviceLabel | str) -> None:
        if xyStageLabel not in self._pydevices:
            return super().stopXYStageSequence(xyStageLabel)
        dev = self._pydevices[xyStageLabel]
        if isinstance(dev, XYStageDevice):
            dev.stop_sequence()

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

    # -- SLM sequencing --

    def getSLMSequenceMaxLength(self, slmLabel: DeviceLabel | str) -> int:
        if slmLabel not in self._pydevices:
            return super().getSLMSequenceMaxLength(slmLabel)
        dev = self._pydevices[slmLabel]
        if isinstance(dev, SLMDevice):
            return dev.get_sequence_max_length()
        return 0

    def loadSLMSequence(
        self,
        slmLabel: DeviceLabel | str,
        imageSequence: Sequence[Any],
    ) -> None:
        if slmLabel not in self._pydevices:
            return super().loadSLMSequence(slmLabel, imageSequence)
        dev = self._pydevices[slmLabel]
        if not isinstance(dev, SLMDevice):
            return
        m = dev.get_sequence_max_length()
        if m == 0:
            raise RuntimeError(f"SLM {slmLabel!r} does not support sequences.")
        shape = dev.shape()
        dtype = np.dtype(dev.dtype())
        arrays: list[Any] = []
        for i, img in enumerate(imageSequence):
            if isinstance(img, bytes):
                arr = np.frombuffer(img, dtype=dtype).reshape(shape)
            else:
                arr = np.asarray(img, dtype=dtype)
                if arr.shape != shape:
                    raise ValueError(
                        f"Image {i} shape {arr.shape} does not match SLM shape {shape}"
                    )
            arrays.append(arr)
        if len(arrays) > m:
            raise ValueError(f"Sequence length {len(arrays)} exceeds maximum {m}.")
        dev.send_sequence(arrays)

    def startSLMSequence(self, slmLabel: DeviceLabel | str) -> None:
        if slmLabel not in self._pydevices:
            return super().startSLMSequence(slmLabel)
        dev = self._pydevices[slmLabel]
        if isinstance(dev, SLMDevice):
            dev.start_sequence()

    def stopSLMSequence(self, slmLabel: DeviceLabel | str) -> None:
        if slmLabel not in self._pydevices:
            return super().stopSLMSequence(slmLabel)
        dev = self._pydevices[slmLabel]
        if isinstance(dev, SLMDevice):
            dev.stop_sequence()


def _values_match(current: Any, expected: Any) -> bool:
    """Compare property values with numeric-aware comparison."""
    if current == expected:
        return True
    try:
        return float(current) == float(expected)
    except (ValueError, TypeError):
        return str(current) == str(expected)
