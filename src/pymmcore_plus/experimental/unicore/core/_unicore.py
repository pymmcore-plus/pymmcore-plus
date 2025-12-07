from __future__ import annotations

import re
import threading
import warnings
from collections.abc import Iterable, Iterator, MutableMapping, Sequence
from contextlib import suppress
from datetime import datetime
from itertools import count
from time import perf_counter_ns
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
    TypeVar,
    cast,
    overload,
    Iterable,
    Union
)

import numpy as np

import pymmcore_plus._pymmcore as pymmcore
from pymmcore_plus.core import CMMCorePlus, DeviceType, Keyword
from pymmcore_plus.core import Keyword as KW
from pymmcore_plus.core._config import Configuration
from pymmcore_plus.core._constants import PixelType, FocusDirection
from pymmcore_plus.experimental.unicore._device_manager import PyDeviceManager
from pymmcore_plus.experimental.unicore._proxy import create_core_proxy
from pymmcore_plus.experimental.unicore.devices._camera import CameraDevice
from pymmcore_plus.experimental.unicore.devices._device_base import Device, SequenceableDevice
from pymmcore_plus.experimental.unicore.devices._shutter import ShutterDevice
from pymmcore_plus.experimental.unicore.devices._slm import SLMDevice
from pymmcore_plus.experimental.unicore.devices._stage import XYStageDevice, _BaseStage, StageDevice
from pymmcore_plus.experimental.unicore.devices._state import StateDevice
from pymmcore_plus.experimental.unicore.devices._register_python_device import REGISTRY_DEVICES

from ._sequence_buffer import SequenceBuffer

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path
    from typing import Literal, NewType

    from numpy.typing import DTypeLike
    from pymmcore import (
        AdapterName,
        AffineTuple,
        ConfigGroupName,
        ConfigPresetName,
        DeviceLabel,
        DeviceName,
        PropertyName,
        StateLabel,
    )

    from pymmcore_plus.core._constants import DeviceInitializationState, PropertyType

    PyDeviceLabel = NewType("PyDeviceLabel", DeviceLabel)
    _T = TypeVar("_T")


class BufferOverflowStop(Exception):
    """Exception raised to signal graceful stop on buffer overflow."""


CURRENT = {
    KW.CoreCamera: None,
    KW.CoreShutter: None,
    KW.CoreFocus: None,
    KW.CoreXYStage: None,
    KW.CoreAutoFocus: None,
    KW.CoreSLM: None,
    KW.CoreGalvo: None,
}


_CACHE_MISS_RE = re.compile(
    r"Property \"(?P<prop>.+?)\" of device \"(?P<dev>.+?)\" not found in cache"
)


class _CoreDevice:
    """A virtual core device.

    This mirrors the pattern used in CMMCore, where there is a virtual "core" device
    that maintains state about various "current" (real) devices.  When a call is made to
    `setSomeThing()` without specifying a device label, the CoreDevice is used to
    determine which real device to use.
    """

    def __init__(self, state_cache: PropertyStateCache) -> None:
        self._state_cache = state_cache
        self._pycurrent: dict[Keyword, PyDeviceLabel | None] = {}
        self.reset_current()

    def reset_current(self) -> None:
        self._pycurrent.update(CURRENT)

    def current(self, keyword: Keyword) -> PyDeviceLabel | None:
        return self._pycurrent[keyword]

    def set_current(self, keyword: Keyword, label: str | None) -> None:
        self._pycurrent[keyword] = cast("PyDeviceLabel", label)
        self._state_cache[(KW.CoreDevice, keyword)] = label


_DEFAULT_BUFFER_SIZE_MB: int = 1000


class UniMMCore(CMMCorePlus):
    """Unified Core object that first checks for python, then C++ devices."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._pydevices = PyDeviceManager()  # manager for python devices
        self._state_cache = PropertyStateCache()  # threadsafe cache for property states
        self._pycore = _CoreDevice(self._state_cache)  # virtual core for python
        self._stop_event: threading.Event = threading.Event()
        self._acquisition_thread: AcquisitionThread | None = None  # TODO: implement
        self._seq_buffer = SequenceBuffer(size_mb=_DEFAULT_BUFFER_SIZE_MB)

        # Python-side config-group storage for UniMMCore devices
        # Structure: { group: { config: [(device, property, value_str), ...] } }
        self._py_config_store: dict[str, dict[str, list[tuple[str, str, str]]]] = {}
        self._py_config_lock = threading.Lock()

        super().__init__(*args, **kwargs)

    def _set_current_if_pydevice(self, keyword: Keyword, label: str) -> str:
        """Helper function to set the current core device if it is a python device.

        If the label is a python device, the current device is set and the label is
        cleared (in preparation for calling `super().setDevice()`), otherwise the
        label is returned unchanged.
        """
        if label in self._pydevices:
            self._pycore.set_current(keyword, label)
            label = ""
        elif not label:
            self._pycore.set_current(keyword, None)
        return label

    # -----------------------------------------------------------------------
    # ------------------------ General Core methods  ------------------------
    # -----------------------------------------------------------------------

    def reset(self) -> None:
        with suppress(TimeoutError):
            self._pydevices.wait_for_device_type(
                DeviceType.AnyType, self.getTimeoutMs(), parallel=False
            )
        super().waitForDeviceType(DeviceType.AnyType)
        self.unloadAllDevices()
        self._pycore.reset_current()
        super().reset()

    # ------------------------------------------------------------------------
    # ----------------- Functionality for All Devices ------------------------
    # ------------------------------------------------------------------------

    def loadDevice(
        self, label: str, moduleName: AdapterName | str, deviceName: DeviceName | str
    ) -> None:
        """Loads a device from the plugin library, or python module.

        In the standard MM case, this will load a device from the plugin library:

        ```python
        core.loadDevice("cam", "DemoCamera", "DCam")
        ```

        For python devices, this will load a device from a python module:

        ```python
        core.loadDevice("pydev", "package.module", "DeviceClass")
        ```

        """
        try:
            CMMCorePlus.loadDevice(self, label, moduleName, deviceName)
        except RuntimeError as e:
            # it was a C++ device, should have worked ... raise the error
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
        """Load a `unicore.Device` as a python device.

        This API allows you to create python-side Device objects that can be used in
        tandem with the C++ devices. Whenever a method is called that would normally
        interact with a C++ device, this class will first check if a python device with
        the same label exists, and if so, use that instead.

        Parameters
        ----------
        label : str
            The label to assign to the device.
        device : unicore.Device
            The device object to load.  Use the appropriate subclass of `Device` for the
            type of device you are creating.
        """
        if label in self.getLoadedDevices():
            raise ValueError(f"The specified device label {label!r} is already in use")
        self._pydevices.load(label, device, create_core_proxy(self))

    load_py_device = loadPyDevice

    def unloadDevice(self, label: DeviceLabel | str) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().unloadDevice(label)
        self._pydevices.unload(label)

    def unloadAllDevices(self) -> None:
        self._pydevices.unload_all()
        super().unloadAllDevices()

    def initializeDevice(self, label: DeviceLabel | str) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().initializeDevice(label)
        self._pydevices.initialize(label)
        # For python StateDevices, seed cache for Label/State to support event emission
        try:
            with self._pydevices[label] as dev:
                # seed using Keyword enums to avoid adapter string handling issues
                try:
                    self._cache_set(label, KW.Label, dev.get_property_value(KW.Label))
                except Exception:  # pragma: no cover - defensive
                    pass
                try:
                    self._cache_set(label, KW.State, dev.get_property_value(KW.State))
                except Exception:  # pragma: no cover - defensive
                    pass
        except Exception:  # pragma: no cover - defensive
            pass
        return None

    def initializeAllDevices(self) -> None:
        # Make idempotent: native core may already be initialized (e.g. after
        # loadSystemConfiguration). Ignore that specific error and proceed to
        # initialize python devices.
        try:
            super().initializeAllDevices()
        except RuntimeError as e:
            msg = str(e).lower()
            if (
                "already initialized" not in msg
                and "initialization already attempted" not in msg
            ):
                raise
        # Initialize python devices and seed cache for StateDevices (Label/State only)
        self._pydevices.initialize_all()
        for lbl in tuple(self._pydevices):
            try:
                with self._pydevices[lbl] as dev:
                    try:
                        self._cache_set(lbl, KW.Label, dev.get_property_value(KW.Label))
                    except Exception:  # pragma: no cover - defensive
                        pass
                    try:
                        self._cache_set(lbl, KW.State, dev.get_property_value(KW.State))
                    except Exception:  # pragma: no cover - defensive
                        pass
            except Exception:  # pragma: no cover - defensive
                pass
        return None

    def _loadSystemConfigurationPython(
            self, fileName: str | Path
    ) -> None:
        """
        Internal method to load a system configuration file.
        This function should work for python and c++ devices.
        """
        # open file and read file
        with open(fileName, "r", encoding='utf8') as config_file:
            list_of_lines = config_file.readlines()  # read lines and save in a list
        config_file.close()  # close file

        for line in list_of_lines:  # iterate over all the list of lines
            if line.startswith("#") or line.startswith('\n'):  # skip comment lines
                continue
            elif line.startswith("Property"):
                new_line = line.strip('\n').split(',')
                if len(new_line) == 4:
                    _, deviceLabel, propName, propValue = new_line
                    try:
                        super().setProperty(deviceLabel, propName, propValue)
                    except Exception:
                        self.setProperty(deviceLabel, propName, propValue)  # check if try/except can be removed
                elif len(new_line) == 3:
                    _, deviceLabel, propName = new_line  # assume propValue is empty string
                    try:
                        super().setProperty(deviceLabel, propName, "")
                    except Exception:
                        self.setProperty(deviceLabel, propName, "")
                else:
                    raise RuntimeError("Invalid Property line format.")
            elif line.startswith("Device"):
                new_line = line.strip('\n').split(',')
                if len(new_line) != 4:
                    raise RuntimeError("Invalid Device line format.")
                # load Device
                _, deviceLabel, moduleName, deviceName = new_line
                try:
                    super().loadDevice(deviceLabel, moduleName, deviceName)
                except Exception:
                    # try python device
                    # print(REGISTRY_DEVICES)
                    # print(deviceName)
                    if deviceLabel in REGISTRY_DEVICES.keys():
                        pyModuleDevice = REGISTRY_DEVICES[deviceLabel]
                        # print(pyModuleDevice)
                        # load the device
                        self.loadPyDevice(deviceLabel,
                                          pyModuleDevice)  # check how to deal with devices with args in their instance
                        # initialize the device
                        self.initializeDevice(deviceLabel)  # see if its better to initialize the device all at once
                        # set initial values for each device
                        if deviceName == "CameraDevice":
                            self.setCameraDevice(deviceLabel)
                        elif deviceName == "StageDevice":
                            self.setFocusDevice(
                                deviceLabel)  # here its assumed that the stage device is the focus device (Z-axes)
                        elif deviceName == "XYStageDevice":
                            self.setXYStageDevice(deviceLabel)
                        elif deviceName == "StateDevice":
                            self.setState(deviceLabel, 0)  # by default always has default value of 0
                        elif deviceName == "SLMDevice":
                            self.setSLMDevice(deviceLabel)
                        elif deviceName == "ShutterDevice":
                            self.setShutterDevice(deviceLabel)
                        else:
                            raise RuntimeError(
                                f"Impossible to set {deviceLabel}. The {deviceName} is not a valid device.")
                        # TODO
                        # check if there other possible devices and check what a sequenceable device does!
                    else:
                        raise RuntimeError(
                            "Device not loaded! Please import your python device or Invalid Device type.")
            elif line.startswith("Label"):
                new_line = line.strip('\n').split(',')
                if len(new_line) != 4:
                    raise RuntimeError("Invalid Label line format.")
                _, deviceLabel, stateInt, stateLabel = new_line
                try:
                    super().defineStateLabel(deviceLabel, int(stateInt), stateLabel)
                except Exception:
                    if deviceLabel in self.getLoadedDevices():
                        self.defineStateLabel(deviceLabel, int(stateInt), stateLabel)
                    else:
                        continue  # skip for the moment, don't know if it's important. It's the case where the device is not loaded yet.
            elif line.startswith("ConfigGroup"):
                new_line = line.strip('\n').split(',')
                if len(new_line) != 6:
                    raise RuntimeError("Invalid ConfigGroup line format.")
                _, configurationGroup, configurationPresets, deviceLabel, propertyName, propertyValue = new_line
                try:
                    super().defineConfig(configurationGroup, configurationPresets, deviceLabel, propertyName,
                                         propertyValue)
                except Exception:
                    self.defineConfig(configurationGroup, configurationPresets, deviceLabel, propertyName,
                                      propertyValue)
                    # in theory deviceLabel, propName and propertyValue could be ""
            elif line.startswith("Delay"):
                new_line = line.strip('\n').split(',')
                if len(new_line) != 3:
                    raise RuntimeError("Invalid line format")
                _, deviceLabel, delayMs = new_line
                try:
                    super().setDeviceDelayMs(deviceLabel, float(delayMs))
                except Exception:
                    self.setDeviceDelayMs(deviceLabel, float(delayMs))
            elif line.startswith("FocusDirection"):
                new_line = line.strip('\n').split(',')
                if len(new_line) != 3:
                    raise RuntimeError("Invalid line format")
                _, deviceLabel, sign = new_line
                try:
                    super().setFocusDirection(deviceLabel, int(sign))
                except Exception:
                    self.setFocusDirection(deviceLabel, int(sign))
            elif line.startswith("ConfigPixelSize"):
                new_line = line.strip('\n').split(',')
                if len(new_line) == 5:
                    _, resolutionID, deviceLabel, propName, value = new_line
                    try:
                        super().definePixelSizeConfig(resolutionID, deviceLabel, propName, value)
                    except Exception:
                        self.definePixelSizeConfig(resolutionID, deviceLabel, propName,
                                                   value)  # CHECK IF WITH UNICORE WORKS
                else:
                    raise RuntimeError("Invalid line format")
            elif line.startswith("PixelSizeum"):
                new_line = line.strip('\n').split(',')
                if len(new_line) != 3:
                    raise RuntimeError("Invalid line format")
                _, resolutionID, pixSize = new_line
                try:
                    super().setPixelSizeUm(resolutionID, float(pixSize))
                except Exception:
                    self.setPixelSizeUm(resolutionID, float(pixSize))  # CHECK IF WITH UNICORE WORKS
            elif line.startswith("PixelSizeAffine"):
                new_line = line.strip('\n').split(',')
                if len(new_line) == 8:
                    _, resolutionID, a11, a12, a13, a21, a22, a23 = new_line
                    try:
                        super().setPixelSizeAffine(resolutionID,
                                                   [float(a11), float(a12), float(a13), float(a21), float(a22),
                                                    float(a23)])
                    except Exception:
                        self.setPixelSizeAffine(resolutionID,
                                                [float(a11), float(a12), float(a13), float(a21), float(a22),
                                                 float(a23)])  # CHECK IF WITH UNICORE WORKS
                else:
                    raise RuntimeError("Invalid line format")
            elif line.startswith("PixelSizedxdz"):
                new_line = line.strip('\n').split(',')
                if len(new_line) == 3:
                    _, resolutionID, dxdz = new_line
                    try:
                        super().setPixelSizedxdz(resolutionID, float(dxdz))
                    except Exception:
                        self.setPixelSizedxdz(resolutionID, float(dxdz))  # CHECK IF WITH UNICORE WORKS
                else:
                    raise RuntimeError("Invalid line format")
            elif line.startswith("PixelSizeydz"):
                new_line = line.strip('\n').split(',')
                if len(new_line) == 3:
                    _, resolutionID, dydz = new_line
                    try:
                        super().setPixelSizedydz(resolutionID, float(dydz))
                    except Exception:
                        self.setPixelSizedydz(resolutionID, float(dydz))  # CHECK IF WITH UNICORE WORKS
                else:
                    raise RuntimeError("Invalid line format")
            elif line.startswith("PixelSizeOptimalZUm"):
                new_line = line.strip('\n').split(',')
                if len(new_line) == 3:
                    _, resolutionID, optimalZUm = new_line
                    try:
                        super().setPixelSizeOptimalZUm(resolutionID, float(optimalZUm))
                    except Exception:
                        self.setPixelSizeOptimalZUm(resolutionID, float(optimalZUm))  # CHECK IF WITH UNICORE WORKS
                else:
                    raise RuntimeError("Invalid line format")
            elif line.startswith("Parent"):
                new_line = line.strip('\n').split(',')
                if len(new_line) != 3:
                    raise RuntimeError("Invalid line format")
                _, deviceLabel, parentHubLabel = line.strip().split(',')
                try:
                    super().setParentLabel(deviceLabel, parentHubLabel)
                except Exception:
                    self.setParentLabel(deviceLabel,
                                        parentHubLabel)  # CHECK IF WITH UNICORE WORKS ... not sure what parent hub could be
            else:
                raise RuntimeError(f"Unexpected line: {line}")
        # verify settings for startup
        # don't know if relevant for us
        # HERE: build system cache...verify what it does
        # skip for now
        self.waitForSystem()
        self.updateSystemStateCache()  # probably to override -> return self.getSystemState()


    def loadSystemConfiguration(
        self, fileName: str | Path = "MMConfig_demo.cfg"
    ) -> None:
        """Load a system config file conforming to the MM .cfg format. Try first a "real" device and then try with python devices."""
        # COPY FROM PYMMCORE-PLUS for the moment
        fpath = Path(fileName).expanduser()
        if not fpath.exists() and not fpath.is_absolute() and self._mm_path:
            fpath = Path(self._mm_path) / fileName
        if not fpath.exists():
            raise FileNotFoundError(f"Path does not exist: {fpath}")
        self._last_sys_config = str(fpath.resolve())
        try:
            super().loadSystemConfiguration(self._last_sys_config)
        except Exception:
            self._loadSystemConfigurationPython(self._last_sys_config)
        with self._py_config_lock:
            self._py_config_store.clear()

    def loadSystemState(self, fileName: str) -> None:
        super().loadSystemState(fileName)
        with self._py_config_lock:
            self._py_config_store.clear()

    def onSystemConfigurationLoaded(self) -> None:
        base = getattr(super(), "onSystemConfigurationLoaded", None)
        if callable(base):  # pragma: no branch
            base()
        with self._py_config_lock:
            self._py_config_store.clear()

    def getDeviceInitializationState(self, label: str) -> DeviceInitializationState:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDeviceInitializationState(label)
        return self._pydevices.get_initialization_state(label)

    def getLoadedDevices(self) -> tuple[DeviceLabel, ...]:
        return tuple(self._pydevices) + tuple(super().getLoadedDevices())

    def getLoadedDevicesOfType(self, devType: int) -> tuple[DeviceLabel, ...]:
        pydevs = self._pydevices.get_labels_of_type(devType)
        return pydevs + super().getLoadedDevicesOfType(devType)

    def getDeviceType(self, label: str) -> DeviceType:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDeviceType(label)
        return self._pydevices[label].type()

    def getDeviceLibrary(self, label: DeviceLabel | str) -> AdapterName:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDeviceLibrary(label)
        return cast("AdapterName", self._pydevices[label].__module__)

    def getDeviceName(self, label: DeviceLabel | str) -> DeviceName:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDeviceName(label)
        return cast("DeviceName", self._pydevices[label].name())

    def getDeviceDescription(self, label: DeviceLabel | str) -> str:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDeviceDescription(label)
        return self._pydevices[label].description()

    # ---------------------------- Properties ---------------------------

    @staticmethod
    def _prop_key(prop: PropertyName | str | Keyword) -> str:
        return str(prop)

    def _cache_set(
        self, device: DeviceLabel | str, prop: PropertyName | str | Keyword, value: Any
    ) -> None:
        self._state_cache[(device, self._prop_key(prop))] = value

    def _py_config_items(
        self, groupName: str, configName: str
    ) -> list[tuple[str, str, str]]:
        with self._py_config_lock:
            return list(self._py_config_store.get(groupName, {}).get(configName, []))

    def _py_entries_with_values(
        self,
        entries: Iterable[tuple[str, str, str]],
        *,
        mode: Literal["stored", "live", "cache"] = "stored",
    ) -> list[tuple[str, str, str]]:
        dedup: dict[tuple[str, str], str] = {}
        for dev, prop, stored in entries:
            key = (dev, prop)
            value: Any = stored
            if mode == "live":
                try:
                    value = self.getProperty(dev, prop)
                except Exception:
                    value = stored
            elif mode == "cache":
                cache_key = (dev, self._prop_key(prop))
                if cache_key in self._state_cache:
                    value = self._state_cache[cache_key]
                else:
                    value = stored
            dedup[key] = str(value)
        return [(dev, prop, val) for (dev, prop), val in dedup.items()]

    def _config_with_py_entries(
        self,
        base_cfg: Any | None,
        entries: list[tuple[str, str, str]],
        *,
        native: bool,
    ) -> Any:
        if native:
            cfg = base_cfg if base_cfg is not None else pymmcore.Configuration()
            for dev, prop, val in entries:
                cfg.addSetting(pymmcore.PropertySetting(dev, prop, val))
            return cfg

        if isinstance(base_cfg, Configuration):
            cfg = Configuration()
            cfg.extend(base_cfg)
        elif base_cfg is not None:
            cfg = Configuration.from_configuration(base_cfg)
        else:
            cfg = Configuration()
        if entries:
            cfg.extend(entries)
        return cfg

    def _system_state_py_entries(
        self, *, use_cache: bool = False
    ) -> list[tuple[str, str, str]]:
        entries: list[tuple[str, str, str]] = []
        for label in tuple(self._pydevices):
            try:
                with self._pydevices[label] as dev:
                    for prop in dev.get_property_names():
                        value: Any
                        if use_cache:
                            key = (label, self._prop_key(prop))
                            if key in self._state_cache:
                                value = self._state_cache[key]
                            else:
                                try:
                                    value = dev.get_property_value(prop)
                                except Exception:
                                    continue
                        else:
                            try:
                                value = dev.get_property_value(prop)
                            except Exception:
                                continue
                        entries.append((label, str(prop), str(value)))
            except Exception:
                continue
        return entries

    def getDevicePropertyNames(
        self, label: DeviceLabel | str
    ) -> tuple[PropertyName, ...]:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDevicePropertyNames(label)
        names = tuple(self._pydevices[label].get_property_names())
        return cast("tuple[PropertyName, ...]", names)

    def hasProperty(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().hasProperty(label, propName)
        return self._pydevices[label].has_property(propName)

    def getProperty(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> Any:  # broadening to Any, because pydevices can return non-string values?
        if label not in self._pydevices:  # pragma: no cover
            return super().getProperty(label, propName)
        with self._pydevices[label] as dev:
            value = dev.get_property_value(propName)
            self._cache_set(label, propName, value)
        return value

    def getPropertyFromCache(
        self, deviceLabel: DeviceLabel | str, propName: PropertyName | str
    ) -> Any:
        if deviceLabel not in self._pydevices:  # pragma: no cover
            return super().getPropertyFromCache(deviceLabel, propName)
        key = (deviceLabel, self._prop_key(propName))
        if key not in self._state_cache:
            prop_str = self._prop_key(propName)
            if prop_str in (str(KW.Label), str(KW.State)):
                try:
                    state_dev = self._py_state(deviceLabel)
                except Exception:
                    state_dev = None
                if state_dev is not None:
                    try:
                        with state_dev:
                            kw = KW.Label if prop_str == str(KW.Label) else KW.State
                            value = state_dev.get_property_value(kw)
                        self._cache_set(deviceLabel, kw, value)
                    except Exception:
                        pass
        return self._state_cache[key]

    def setProperty(
        self, label: str, propName: str, propValue: bool | float | int | str
    ) -> None:
        """Set a property on either a native or python device.

        - For python devices, set directly on the device and update the python-side
          cache. Use the CMMCorePlus emission helper for consistent signals.
        - For native devices, pre-seed critical cache entries for python state devices
          to avoid cache-miss during native-side operations that consult cache, then
          delegate to the superclass.
        """
        if label in self._pydevices:
            # Python device path
            # Ensure events.propertyChanged mirrors native behavior
            with self._property_change_emission_ensured(label, (propName,)):
                with self._pydevices[label] as dev:
                    dev.set_property_value(propName, propValue)
                    self._cache_set(label, propName, propValue)
            return None

        # Native device path: seed cache for python StateDevices (Label/State)
        def _seed_state_cache() -> None:
            for lbl in tuple(self._pydevices):
                try:
                    with self._pydevices.get_device_of_type(
                        lbl, StateDevice
                    ) as state_dev:
                        try:
                            val = state_dev.get_property_value(KW.Label)
                            self._cache_set(lbl, KW.Label, val)
                        except Exception:  # pragma: no cover - defensive
                            pass
                        try:
                            val = state_dev.get_property_value(KW.State)
                            self._cache_set(lbl, KW.State, val)
                        except Exception:  # pragma: no cover - defensive
                            pass
                except Exception:  # pragma: no cover - defensive
                    continue

        _seed_state_cache()
        try:
            return super().setProperty(label, propName, propValue)
        except ValueError as e:
            # In case native path consulted cache mid-operation before seeding
            msg = str(e)
            if "not found in cache" in msg:
                match = _CACHE_MISS_RE.search(msg)
                if match:
                    dev_label = match.group("dev")
                    prop = match.group("prop")
                    if dev_label in self._pydevices:
                        # ensure cache populated for the referenced python state device
                        if prop == str(KW.Label):
                            try:
                                with self._pydevices.get_device_of_type(
                                    dev_label, StateDevice
                                ) as sdev:
                                    self._cache_set(
                                        dev_label,
                                        KW.Label,
                                        sdev.get_property_value(KW.Label),
                                    )
                            except Exception:  # pragma: no cover - defensive
                                pass
                        elif prop == str(KW.State):
                            try:
                                with self._pydevices.get_device_of_type(
                                    dev_label, StateDevice
                                ) as sdev:
                                    self._cache_set(
                                        dev_label,
                                        KW.State,
                                        sdev.get_property_value(KW.State),
                                    )
                            except Exception:  # pragma: no cover - defensive
                                pass
                        # If native call already set the value, emit event and exit
                        current_val: Any | None
                        try:
                            current_val = self.getProperty(label, propName)
                        except Exception:
                            current_val = None
                        if current_val is not None and str(current_val) == str(
                            propValue
                        ):
                            try:
                                self.events.propertyChanged.emit(
                                    label, self._prop_key(propName), current_val
                                )
                            except Exception:
                                pass
                            return None
                _seed_state_cache()
                return super().setProperty(label, propName, propValue)
            raise

    def getPropertyType(self, label: str, propName: str) -> PropertyType:
        if label not in self._pydevices:  # pragma: no cover
            return super().getPropertyType(label, propName)
        return self._pydevices[label].get_property_info(propName).type

    def hasPropertyLimits(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().hasPropertyLimits(label, propName)
        with self._pydevices[label] as dev:
            return dev.get_property_info(propName).limits is not None

    def getPropertyLowerLimit(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> float:
        if label not in self._pydevices:  # pragma: no cover
            return super().getPropertyLowerLimit(label, propName)
        with self._pydevices[label] as dev:
            if lims := dev.get_property_info(propName).limits:
                return lims[0]
            return 0

    def getPropertyUpperLimit(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> float:
        if label not in self._pydevices:  # pragma: no cover
            return super().getPropertyUpperLimit(label, propName)
        with self._pydevices[label] as dev:
            if lims := dev.get_property_info(propName).limits:
                return lims[1]
            return 0

    def getAllowedPropertyValues(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> tuple[str, ...]:
        if label not in self._pydevices:  # pragma: no cover
            return super().getAllowedPropertyValues(label, propName)
        with self._pydevices[label] as dev:
            return tuple(dev.get_property_info(propName).allowed_values or ())

    def isPropertyPreInit(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().isPropertyPreInit(label, propName)
        with self._pydevices[label] as dev:
            return dev.get_property_info(propName).is_pre_init

    def isPropertyReadOnly(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().isPropertyReadOnly(label, propName)
        with self._pydevices[label] as dev:
            return dev.is_property_read_only(propName)

    def isPropertySequenceable(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().isPropertySequenceable(label, propName)
        with self._pydevices[label] as dev:
            return dev.is_property_sequenceable(propName)

    def getPropertySequenceMaxLength(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> int:
        if label not in self._pydevices:  # pragma: no cover
            return super().getPropertySequenceMaxLength(label, propName)
        with self._pydevices[label] as dev:
            return dev.get_property_info(propName).sequence_max_length

    def loadPropertySequence(
        self,
        label: DeviceLabel | str,
        propName: PropertyName | str,
        eventSequence: Sequence[Any],
    ) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().loadPropertySequence(label, propName, eventSequence)
        with self._pydevices[label] as dev:
            dev.load_property_sequence(propName, eventSequence)

    def startPropertySequence(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().startPropertySequence(label, propName)
        with self._pydevices[label] as dev:
            dev.start_property_sequence(propName)

    def stopPropertySequence(
        self, label: DeviceLabel | str, propName: PropertyName | str
    ) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().stopPropertySequence(label, propName)
        with self._pydevices[label] as dev:
            dev.stop_property_sequence(propName)

    # ------------------------------ Ready State ----------------------------

    def deviceBusy(self, label: DeviceLabel | str) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().deviceBusy(label)
        with self._pydevices[label] as dev:
            return dev.busy()

    def waitForDevice(self, label: DeviceLabel | str) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().waitForDevice(label)
        self._pydevices.wait_for(label, self.getTimeoutMs())

    def waitForConfig(self, group: str, configName: str) -> None:
        """Wait for all devices referenced in `group/configName` to be ready."""
        try:
            super().waitForConfig(group, configName)
        except Exception:
            # Ignore native errors; python fallback will handle relevant devices
            pass

        py_items = self._py_config_items(group, configName)
        for dev, _, _ in py_items:
            if dev in self._pydevices:
                try:
                    self.waitForDevice(dev)
                except Exception:
                    continue

    # probably only needed because C++ method is not virtual
    def systemBusy(self) -> bool:
        return self.deviceTypeBusy(DeviceType.AnyType)

    # probably only needed because C++ method is not virtual
    def waitForSystem(self) -> None:
        self.waitForDeviceType(DeviceType.AnyType)

    def waitForDeviceType(self, devType: int) -> None:
        super().waitForDeviceType(devType)
        self._pydevices.wait_for_device_type(devType, self.getTimeoutMs())

    def deviceTypeBusy(self, devType: int) -> bool:
        if super().deviceTypeBusy(devType):
            return True  # pragma: no cover

        for label in self._pydevices.get_labels_of_type(devType):
            with self._pydevices[label] as dev:
                if dev.busy():
                    return True
        return False

    # ########################################################################
    # ------------------------ Config Group Methods ------------------------
    # ########################################################################

    def defineConfigGroup(self, groupName: str) -> None:
        """Define a configuration group.

        Native-first: attempt the C++ implementation, then ensure the Python-side
        store contains the group for UniMMCore python devices.
        """
        try:
            return super().defineConfigGroup(groupName)
        except Exception:
            # Fall back to python-side store
            with self._py_config_lock:
                self._py_config_store.setdefault(groupName, {})

    def renameConfigGroup(self, oldGroupName: str, newGroupName: str) -> None:
        """Rename a configuration group, including python-side configs."""
        try:
            super().renameConfigGroup(oldGroupName, newGroupName)
        except Exception:
            pass
        if oldGroupName == newGroupName:
            return
        with self._py_config_lock:
            group = self._py_config_store.pop(oldGroupName, None)
            if group is not None:
                existing = self._py_config_store.setdefault(newGroupName, {})
                existing.update(group)

    def defineConfig(
        self,
        groupName: str,
        configName: str,
        deviceLabel: str | None = None,
        propName: str | None = None,
        value: Any | None = None,
    ) -> None:
        """Define a config, optionally with a device/property/value entry.

        - Always record in the Python store when a full triplet is provided,
          so UniMMCore devices are supported.
        - Attempt the native call (2-arg or 5-arg form) to support C++ devices.
        """
        # Record in python-side store if we have a full (device, prop, value)
        if (deviceLabel is not None) and (propName is not None) and (value is not None):
            with self._py_config_lock:
                group = self._py_config_store.setdefault(groupName, {})
                cfg_list = group.setdefault(configName, [])
                cfg_list.append((deviceLabel, propName, str(value)))
        else:
            # Ensure group exists for 2-arg usage
            with self._py_config_lock:
                self._py_config_store.setdefault(groupName, {})

        # Try native implementation
        try:
            if (deviceLabel is None) and (propName is None) and (value is None):
                super().defineConfig(groupName, configName)
            else:
                assert deviceLabel is not None
                assert propName is not None
                super().defineConfig(
                    groupName,
                    configName,
                    deviceLabel,
                    propName,
                    str(value),
                )
        except Exception:  # pragma: no cover - native may reject python devices
            return None
        return None

    def getAvailableConfigGroups(self) -> tuple[ConfigGroupName, ...]:
        """Return available configuration groups (native + python)."""
        native: tuple[ConfigGroupName, ...]
        try:
            native = super().getAvailableConfigGroups()
        except Exception:
            native = ()
        with self._py_config_lock:
            py_groups = tuple(self._py_config_store.keys())
        # Deduplicate while preserving order (native first)
        seen: set[str] = set()
        out: list[str] = []
        for g in (*native, *py_groups):
            if g not in seen:
                seen.add(g)
                out.append(g)
        return cast("tuple[ConfigGroupName, ...]", tuple(out))

    def getAvailableConfigs(self, groupName: str) -> tuple[ConfigPresetName, ...]:
        """Return available config names for a group (native + python)."""
        native: tuple[ConfigPresetName, ...]
        try:
            native = super().getAvailableConfigs(groupName)
        except Exception:
            native = ()
        with self._py_config_lock:
            py_cfgs = tuple(self._py_config_store.get(groupName, {}).keys())
        seen: set[str] = set()
        out: list[str] = []
        for c in (*native, *py_cfgs):
            if c not in seen:
                seen.add(c)
                out.append(c)
        return cast("tuple[ConfigPresetName, ...]", tuple(out))

    def isConfigDefined(self, groupName: str, configName: str) -> bool:
        if super().isConfigDefined(groupName, configName):
            return True
        with self._py_config_lock:
            return configName in self._py_config_store.get(groupName, {})

    def deleteConfig(
        self,
        groupName: ConfigGroupName | str,
        configName: ConfigPresetName | str,
        deviceLabel: DeviceLabel | str | None = None,
        propName: PropertyName | str | None = None,
    ) -> None:
        """Delete a configuration in a group (native + python)."""
        try:
            if deviceLabel is not None and propName is not None:
                super().deleteConfig(groupName, configName, deviceLabel, propName)
            else:
                super().deleteConfig(groupName, configName)
        except Exception:
            # ignore native failures
            pass
        with self._py_config_lock:
            if groupName in self._py_config_store:
                self._py_config_store[groupName].pop(configName, None)

    def deleteConfigGroup(self, groupName: ConfigGroupName | str) -> None:
        """Delete an entire configuration group (native + python)."""
        try:
            super().deleteConfigGroup(groupName)
        except Exception:
            pass
        with self._py_config_lock:
            self._py_config_store.pop(groupName, None)

    def renameConfig(self, groupName: str, oldName: str, newName: str) -> None:
        """Rename a configuration (native + python)."""
        try:
            super().renameConfig(groupName, oldName, newName)
        except Exception:
            # ignore native failures
            pass
        with self._py_config_lock:
            group = self._py_config_store.get(groupName)
            if group and oldName in group and newName != oldName:
                group[newName] = group.pop(oldName)

    def getConfigGroupState(
        self,
        group: ConfigGroupName | str,
        *,
        native: bool = False,
    ) -> Any:
        """Return the state of devices included in `group`.

        - Prefer native when available. If native fails and native=True, re-raise.
        - If native is False, and native fails, return a mapping of current properties
          for devices referenced by this group's python configs.
        """
        try:
            if native:
                return super().getConfigGroupState(group, native=True)
            return super().getConfigGroupState(group)
        except Exception:
            if native:
                # Respect contract: if native requested and not available, bubble up
                raise
            # Build mapping from python store
            with self._py_config_lock:
                group_cfgs = list(self._py_config_store.get(group, {}).values())
            devices: dict[str, dict[str, Any]] = {}
            for cfg_items in group_cfgs:
                for dev, prop, _ in cfg_items:
                    dev_map = devices.setdefault(dev, {})
                    try:
                        dev_map[prop] = self.getProperty(dev, prop)
                    except Exception:
                        dev_map[prop] = None
            return devices

    def setConfig(self, group: str, configName: str) -> None:
        """Set the configuration `configName` in `group`.

        Native-first; if native fails, apply python-side stored properties.
        For state devices, apply via setState/setStateLabel when appropriate.
        """
        try:
            return super().setConfig(group, configName)
        except Exception:
            pass

        with self._py_config_lock:
            cfg_items = list(self._py_config_store.get(group, {}).get(configName, []))

        for dev, prop, val_str in cfg_items:
            # Heuristics for state devices
            if prop == str(KW.State) or prop == "State":
                try:
                    self.setState(dev, int(val_str))
                    # update cache for cached current-config detection
                    self._cache_set(dev, prop, val_str)
                    continue
                except Exception:
                    # Fallback to property if setState not applicable
                    pass
            if prop == str(KW.Label) or prop == "Label":
                try:
                    self.setStateLabel(dev, val_str)
                    # update cache for cached current-config detection
                    self._cache_set(dev, prop, val_str)
                    continue
                except Exception:
                    pass
            # Generic property set
            self.setProperty(dev, prop, val_str)

    def onConfigGroupChanged(self, groupName: str, newConfigName: str) -> None:
        base = getattr(super(), "onConfigGroupChanged", None)
        if callable(base):  # pragma: no branch
            base(groupName, newConfigName)
        extras = self._py_entries_with_values(
            self._py_config_items(groupName, newConfigName)
        )
        for dev, prop, val in extras:
            self._cache_set(dev, prop, val)

    # ----------------------------- Config Introspection -----------------------------

    def getConfigGroupStateFromCache(
        self,
        group: ConfigGroupName | str,
        *,
        native: bool = False,
    ) -> Any:
        base_cfg_native: pymmcore.Configuration | None = None
        try:
            base_cfg_native = super().getConfigGroupStateFromCache(group, native=True)
        except Exception:
            base_cfg_native = None

        with self._py_config_lock:
            group_cfgs = list(self._py_config_store.get(group, {}).values())
        extras = self._py_entries_with_values(
            (item for cfg in group_cfgs for item in cfg), mode="cache"
        )

        if not extras and base_cfg_native is not None:
            return (
                base_cfg_native
                if native
                else Configuration.from_configuration(base_cfg_native)
            )
        if not extras and base_cfg_native is None:
            if native:
                raise RuntimeError(
                    f"Config group {group!r} not available in native cache"
                )
            raise RuntimeError(f"Config group {group!r} not available in python cache")

        if native:
            cfg_native = (
                base_cfg_native
                if base_cfg_native is not None
                else pymmcore.Configuration()
            )
            for dev, prop, val in extras:
                cfg_native.addSetting(pymmcore.PropertySetting(dev, prop, val))
            return cfg_native

        cfg = Configuration()
        if base_cfg_native is not None:
            cfg.extend(base_cfg_native)
        cfg.extend(extras)
        return cfg

    def getConfigState(
        self,
        groupName: ConfigGroupName | str,
        configName: ConfigPresetName | str,
        *,
        native: bool = False,
    ) -> Any:
        """Return the state for a specific config in a group.

        Native-first. If native fails and native=True, re-raise. Otherwise return a
        python mapping of {device: {prop: value}} built from the stored config data,
        reflecting the stored values (not the live values).
        """
        try:
            if native:
                return super().getConfigState(groupName, configName, native=True)
            return super().getConfigState(groupName, configName, native=False)
        except Exception:
            if native:
                raise
            with self._py_config_lock:
                items = list(
                    self._py_config_store.get(groupName, {}).get(configName, [])
                )
            devices: dict[str, dict[str, Any]] = {}
            for dev, prop, val in items:
                devices.setdefault(dev, {})[prop] = val
            return devices

    def getConfigData(
        self,
        groupName: ConfigGroupName | str,
        configName: ConfigPresetName | str,
        *,
        native: bool = False,
    ) -> Any:
        """Return the raw config data tuples for a group/config.

        Native-first. Python fallback returns a tuple of (device, property, value)
        strings from the python-side store.
        """
        try:
            base_cfg_native = super().getConfigData(groupName, configName, native=True)
        except Exception:
            base_cfg_native = None

        extras = self._py_entries_with_values(
            self._py_config_items(groupName, configName)
        )

        if not extras:
            if base_cfg_native is None:
                detail = "no native data" if native else "no data"
                message = f"Config {configName!r} in group {groupName!r} has {detail}"
                raise RuntimeError(message)
            return (
                base_cfg_native
                if native
                else Configuration.from_configuration(base_cfg_native)
            )

        if base_cfg_native is None:
            base_cfg_native = pymmcore.Configuration()
        for dev, prop, val in extras:
            base_cfg_native.addSetting(pymmcore.PropertySetting(dev, prop, val))

        if native:
            return base_cfg_native
        cfg = Configuration.from_configuration(base_cfg_native)
        return cfg

    def _config_matches_current(
        self, groupName: str, configName: str, *, use_cache: bool
    ) -> bool:
        with self._py_config_lock:
            items = list(self._py_config_store.get(groupName, {}).get(configName, []))
        for dev, prop, val_str in items:
            try:
                key = (dev, self._prop_key(prop))
                if use_cache and key in self._state_cache:
                    current_val = self._state_cache[key]
                else:
                    current_val = self.getProperty(dev, prop)
            except Exception:
                return False
            if str(current_val) != str(val_str):
                return False
        return True

    def getCurrentConfig(
        self, groupName: ConfigGroupName | str
    ) -> ConfigPresetName | Literal[""]:
        """Return the name of the current config in `groupName`.

        Native-first with validation: if native returns a name that doesn't match the
        python-store criteria (or the group has python-only configs), prefer the
        python-derived match. Returns an empty string if none match.
        """
        native_name: ConfigPresetName | Literal[""] | None = None
        try:
            native_name = super().getCurrentConfig(groupName)
        except Exception:
            native_name = None

        # Compute python-side match
        py_match: ConfigPresetName | Literal[""] = ""
        for cfg_name in self.getAvailableConfigs(groupName):
            if self._config_matches_current(groupName, cfg_name, use_cache=False):
                py_match = cfg_name
                break

        # If we have a python match, prefer it when group has python configs or when
        # native_name doesn't match current python-observed state
        with self._py_config_lock:
            group_has_py = groupName in self._py_config_store and bool(
                self._py_config_store[groupName]
            )

        if py_match:
            if group_has_py:
                return py_match
            # If no python configs, but native_name matches python-observed state,
            # prefer the native answer to avoid surprises.
            if native_name and native_name == py_match:
                return native_name
            return py_match

        # No python-derived match; fall back to native if available
        if native_name:
            return native_name
        return ""

    def getSystemState(
        self, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        native_cfg: pymmcore.Configuration = super().getSystemState(native=True)
        extras = self._system_state_py_entries(use_cache=False)
        if not extras:
            return (
                native_cfg if native else Configuration.from_configuration(native_cfg)
            )
        if native:
            for dev, prop, val in extras:
                native_cfg.addSetting(pymmcore.PropertySetting(dev, prop, val))
            return native_cfg
        cfg = Configuration.from_configuration(native_cfg)
        cfg.extend(extras)
        return cfg

    @overload
    def getSystemStateCache(
        self, *, native: Literal[True]
    ) -> pymmcore.Configuration: ...

    @overload
    def getSystemStateCache(
        self, *, native: Literal[False] = False
    ) -> Configuration: ...

    def getSystemStateCache(
        self, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        native_cfg: pymmcore.Configuration = super().getSystemStateCache(native=True)
        extras = self._system_state_py_entries(use_cache=True)
        if not extras:
            return (
                native_cfg if native else Configuration.from_configuration(native_cfg)
            )
        if native:
            for dev, prop, val in extras:
                native_cfg.addSetting(pymmcore.PropertySetting(dev, prop, val))
            return native_cfg
        cfg = Configuration.from_configuration(native_cfg)
        cfg.extend(extras)
        return cfg

    def getCurrentConfigFromCache(
        self, groupName: ConfigGroupName | str
    ) -> ConfigPresetName | Literal[""]:
        """Return the current config using cached properties when possible.

        Native-first with validation; prefer python-derived match when group has
        python configs or native result doesn't reflect python-observed state.
        """
        native_name: ConfigPresetName | Literal[""] | None = None
        try:
            native_name = super().getCurrentConfigFromCache(groupName)
        except Exception:
            native_name = None

        py_match: ConfigPresetName | Literal[""] = ""
        for cfg_name in self.getAvailableConfigs(groupName):
            if self._config_matches_current(groupName, cfg_name, use_cache=True):
                py_match = cfg_name
                break

        with self._py_config_lock:
            group_has_py = groupName in self._py_config_store and bool(
                self._py_config_store[groupName]
            )

        if py_match:
            if group_has_py:
                return py_match
            if native_name and native_name == py_match:
                return native_name
            return py_match

        if native_name:
            return native_name
        return ""

    def getDeviceDelayMs(self, label: DeviceLabel | str) -> float:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDeviceDelayMs(label)
        return 0  # pydevices don't yet support delays

    def setDeviceDelayMs(self, label: DeviceLabel | str, delayMs: float) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().setDeviceDelayMs(label, delayMs)
        if delayMs != 0:  # pragma: no cover
            raise NotImplementedError("Python devices do not support delays")

    def usesDeviceDelay(self, label: DeviceLabel | str) -> bool:
        if label not in self._pydevices:  # pragma: no cover
            return super().usesDeviceDelay(label)
        return False

    # ########################################################################
    # ---------------------------- XYStageDevice -----------------------------
    # ########################################################################

    def setXYStageDevice(self, xyStageLabel: DeviceLabel | str) -> None:
        label = self._set_current_if_pydevice(KW.CoreXYStage, xyStageLabel)
        super().setXYStageDevice(label)

    def getXYStageDevice(self) -> DeviceLabel | Literal[""]:
        """Returns the label of the currently selected XYStage device.

        Returns empty string if no XYStage device is selected.
        """
        return self._pycore.current(KW.CoreXYStage) or super().getXYStageDevice()

    @overload
    def setXYPosition(self, x: float, y: float, /) -> None: ...
    @overload
    def setXYPosition(
        self, xyStageLabel: DeviceLabel | str, x: float, y: float, /
    ) -> None: ...
    def setXYPosition(self, *args: Any) -> None:
        """Sets the position of the XY stage in microns."""
        label, args = _ensure_label(args, min_args=3, getter=self.getXYStageDevice)
        if label not in self._pydevices:  # pragma: no cover
            return super().setXYPosition(label, *args)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.set_position_um(*args)

    @overload
    def getXYPosition(self) -> tuple[float, float]: ...
    @overload
    def getXYPosition(self, xyStageLabel: DeviceLabel | str) -> tuple[float, float]: ...
    def getXYPosition(
        self, xyStageLabel: DeviceLabel | str = ""
    ) -> tuple[float, float]:
        """Obtains the current position of the XY stage in microns."""
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:  # pragma: no cover
            return tuple(super().getXYPosition(label))  # type: ignore

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            return dev.get_position_um()

    # reimplementation needed because the C++ method are not virtual
    @overload
    def getXPosition(self) -> float: ...
    @overload
    def getXPosition(self, xyStageLabel: DeviceLabel | str) -> float: ...
    def getXPosition(self, xyStageLabel: DeviceLabel | str = "") -> float:
        """Obtains the current position of the X axis of the XY stage in microns."""
        return self.getXYPosition(xyStageLabel)[0]

    # reimplementation needed because the C++ method are not virtual
    @overload
    def getYPosition(self) -> float: ...
    @overload
    def getYPosition(self, xyStageLabel: DeviceLabel | str) -> float: ...
    def getYPosition(self, xyStageLabel: DeviceLabel | str = "") -> float:
        """Obtains the current position of the Y axis of the XY stage in microns."""
        return self.getXYPosition(xyStageLabel)[1]

    def getXYStageSequenceMaxLength(self, xyStageLabel: DeviceLabel | str) -> int:
        """Gets the maximum length of an XY stage's position sequence."""
        if xyStageLabel not in self._pydevices:  # pragma: no cover
            return super().getXYStageSequenceMaxLength(xyStageLabel)
        dev = self._pydevices.get_device_of_type(xyStageLabel, XYStageDevice)
        return dev.get_sequence_max_length()

    def isXYStageSequenceable(self, xyStageLabel: DeviceLabel | str) -> bool:
        """Queries XY stage if it can be used in a sequence."""
        if xyStageLabel not in self._pydevices:  # pragma: no cover
            return super().isXYStageSequenceable(xyStageLabel)
        dev = self._pydevices.get_device_of_type(xyStageLabel, XYStageDevice)
        return dev.is_sequenceable()

    def loadXYStageSequence(
        self,
        xyStageLabel: DeviceLabel | str,
        xSequence: Sequence[float],
        ySequence: Sequence[float],
        /,
    ) -> None:
        """Transfer a sequence of stage positions to the xy stage.

        xSequence and ySequence must have the same length. This should only be called
        for XY stages that are sequenceable
        """
        if xyStageLabel not in self._pydevices:  # pragma: no cover
            return super().loadXYStageSequence(xyStageLabel, xSequence, ySequence)
        if len(xSequence) != len(ySequence):
            raise ValueError("xSequence and ySequence must have the same length")
        dev = self._pydevices.get_device_of_type(xyStageLabel, XYStageDevice)
        seq = tuple(zip(xSequence, ySequence))
        if len(seq) > dev.get_sequence_max_length():
            raise ValueError(
                f"Sequence is too long. Max length is {dev.get_sequence_max_length()}"
            )
        dev.send_sequence(seq)

    @overload
    def setOriginX(self) -> None: ...
    @overload
    def setOriginX(self, xyStageLabel: DeviceLabel | str) -> None: ...
    def setOriginX(self, xyStageLabel: DeviceLabel | str = "") -> None:
        """Zero the given XY stage's X coordinate at the current position."""
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:  # pragma: no cover
            return super().setOriginX(label)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.set_origin_x()

    @overload
    def setOriginY(self) -> None: ...
    @overload
    def setOriginY(self, xyStageLabel: DeviceLabel | str) -> None: ...
    def setOriginY(self, xyStageLabel: DeviceLabel | str = "") -> None:
        """Zero the given XY stage's Y coordinate at the current position."""
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:  # pragma: no cover
            return super().setOriginY(label)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.set_origin_y()

    @overload
    def setOriginXY(self) -> None: ...
    @overload
    def setOriginXY(self, xyStageLabel: DeviceLabel | str) -> None: ...
    def setOriginXY(self, xyStageLabel: DeviceLabel | str = "") -> None:
        """Zero the given XY stage's coordinates at the current position."""
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:  # pragma: no cover
            return super().setOriginXY(label)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.set_origin()

    @overload
    def setAdapterOriginXY(self, newXUm: float, newYUm: float, /) -> None: ...
    @overload
    def setAdapterOriginXY(
        self, xyStageLabel: DeviceLabel | str, newXUm: float, newYUm: float, /
    ) -> None: ...
    def setAdapterOriginXY(self, *args: Any) -> None:
        """Enable software translation of coordinates for the current XY stage.

        The current position of the stage becomes (newXUm, newYUm). It is recommended
        that setOriginXY() be used instead where available.
        """
        label, args = _ensure_label(args, min_args=3, getter=self.getXYStageDevice)
        if label not in self._pydevices:  # pragma: no cover
            return super().setAdapterOriginXY(label, *args)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.set_adapter_origin_um(*args)

    @overload
    def setRelativeXYPosition(self, dx: float, dy: float, /) -> None: ...
    @overload
    def setRelativeXYPosition(
        self, xyStageLabel: DeviceLabel | str, dx: float, dy: float, /
    ) -> None: ...
    def setRelativeXYPosition(self, *args: Any) -> None:
        """Sets the relative position of the XY stage in microns."""
        label, args = _ensure_label(args, min_args=3, getter=self.getXYStageDevice)
        if label not in self._pydevices:  # pragma: no cover
            return super().setRelativeXYPosition(label, *args)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.set_relative_position_um(*args)

    def startXYStageSequence(self, xyStageLabel: DeviceLabel | str) -> None:
        """Starts an ongoing sequence of triggered events in an XY stage.

        This should only be called for stages that are sequenceable
        """
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:  # pragma: no cover
            return super().startXYStageSequence(label)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.start_sequence()

    def stopXYStageSequence(self, xyStageLabel: DeviceLabel | str) -> None:
        """Stops an ongoing sequence of triggered events in an XY stage.

        This should only be called for stages that are sequenceable
        """
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:  # pragma: no cover
            return super().stopXYStageSequence(label)

        with self._pydevices.get_device_of_type(label, XYStageDevice) as dev:
            dev.stop_sequence()

    # ########################################################################
    # ----------------------------- StageDevice ------------------------------
    # ########################################################################
    def getFocusDevice(self) -> PyDeviceLabel | DeviceLabel | Literal[""] | None:
        """Return the current Focus Device"""
        return self._pycore.current(KW.CoreFocus) or super().getFocusDevice()

    def setFocusDevice(self, focusLabel: str) -> None:
        """Set new current Focus Device"""
        try:
            super().setFocusDevice(focusLabel)
        except Exception:
            # python device
            if focusLabel in self._pydevices:
                if self.getDeviceType(focusLabel) == DeviceType.StageDevice:
                    # assign focus device
                    label = self._set_current_if_pydevice(KW.CoreFocus, focusLabel)
                    super().setFocusDevice(label)
        # otherwise do nothing

    def getPosition(self, stageName: DeviceLabel | str | None) -> float:
        label = stageName
        if label == "":
            raise RuntimeError(f"Failed to retrieve Z position for {self}")
        elif label is None:
            label = self.getFocusDevice()

        if label not in self._pydevices:
            return super().getPosition()
        with self._pydevices.get_device_of_type(label, StageDevice) as device:
            return device.get_position_um()


    def setPosition(self, stageLabel: DeviceLabel | str | None, position: float) -> None:
        label = stageLabel
        if label == "":
            raise RuntimeError(f"Failed to set Z position for {self}")
        elif label is None:
            label = self.getFocusDevice()

        if label not in self._pydevices:
            super().setPosition(position)
        with self._pydevices.get_device_of_type(label, StageDevice) as device:
            device.set_position_um(position)

    def setZPosition(self, val: float) -> None:
        """Set the position of the current  focus device in microns. If fails, it will try to use the python focus device."""
        try:
            super().setZPosition(val)
        except Exception:
            # python focus Device
            self.setPosition(self.getFocusDevice(), val)

    def getZPosition(self) -> float:
        """ Get the position of the current focus device in microns. If fails, it will try to use the python focus device."""
        try:
            return super().getZPosition()
        except Exception:
            # python focus device
            return self.getPosition(self.getFocusDevice())

    def setFocusDirection(self, stageLabel: DeviceLabel | str, sign: int) -> None:
        """Set the focus direction of the Z stage"""
        if stageLabel == "" or stageLabel != self.getFocusDevice():
            raise RuntimeError(f"Failed to set new FocusDirection: No {stageLabel} as Focus Device.")
        if stageLabel not in self._pydevices:
            super().setFocusDirection(stageLabel, sign)
        
        with self._pydevices.get_device_of_type(stageLabel, StageDevice) as device:
            device.set_focus_direction(sign)

    def getFocusDirection(self, stageLabel: DeviceLabel | str) -> FocusDirection:
        """Get the current focus direction of the Z stage"""
        if stageLabel == "" or stageLabel != self.getFocusDevice():
            raise RuntimeError(f"Failed to retrieve Focus direction: No {stageLabel} as Focus Device.")
        if stageLabel not in self._pydevices:
            return super().getFocusDirection(stageLabel)
        with self._pydevices.get_device_of_type(stageLabel, StageDevice) as device:
            return device.get_focus_direction()

    def setOrigin(self):
        """Zero the current focus/Z stage's coordinates at the current position."""
        try:
            super().setOrigin()
        except Exception:
            z_stage = self.getFocusDevice()
            with self._pydevices.get_device_of_type(z_stage, StageDevice) as device:
                device.set_origin()


    # -----------------------------------------------------------------------
    # ---------------------------- Any Stage --------------------------------
    # -----------------------------------------------------------------------

    def home(self, xyOrZStageLabel: DeviceLabel | str) -> None:
        """Perform a hardware homing operation for an XY or focus/Z stage."""
        if xyOrZStageLabel not in self._pydevices:
            return super().home(xyOrZStageLabel)

        dev = self._pydevices.get_device_of_type(xyOrZStageLabel, _BaseStage)
        dev.home()

    def stop(self, xyOrZStageLabel: DeviceLabel | str) -> None:
        """Stop the XY or focus/Z stage."""
        if xyOrZStageLabel not in self._pydevices:
            return super().stop(xyOrZStageLabel)

        dev = self._pydevices.get_device_of_type(xyOrZStageLabel, _BaseStage)
        dev.stop()

    # ########################################################################
    # ------------------------ Camera Device Methods -------------------------
    # ########################################################################

    # --------------------------------------------------------------------- utils

    def _py_camera(self, cameraLabel: str | None = None) -> CameraDevice | None:
        """Return the *Python* Camera for ``label`` (or current), else ``None``."""
        label = cameraLabel or self.getCameraDevice()
        if label in self._pydevices:
            return self._pydevices.get_device_of_type(label, CameraDevice)
        return None

    def setCameraDevice(self, cameraLabel: DeviceLabel | str) -> None:
        """Set the camera device."""
        label = self._set_current_if_pydevice(KW.CoreCamera, cameraLabel)
        super().setCameraDevice(label)

    def getCameraDevice(self) -> DeviceLabel | Literal[""]:
        """Returns the label of the currently selected camera device.

        Returns empty string if no camera device is selected.
        """
        return self._pycore.current(KW.CoreCamera) or super().getCameraDevice()

    # --------------------------------------------------------------------- snap

    _current_image_buffer: np.ndarray | None = None

    def _do_snap_image(self) -> None:
        if (cam := self._py_camera()) is None:
            return pymmcore.CMMCore.snapImage(self)

        buf = None

        def _get_buffer(shape: Sequence[int], dtype: DTypeLike) -> np.ndarray:
            """Get a buffer for the camera image."""
            nonlocal buf
            buf = np.empty(shape, dtype=dtype)
            return buf

        # synchronous call - consume one item from the generator
        with cam:
            for _ in cam.start_sequence(1, get_buffer=_get_buffer):
                if buf is not None:
                    self._current_image_buffer = buf
                else:  # pragma: no cover  #  bad camera implementation
                    warnings.warn(
                        "Camera device did not provide an image buffer.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                return

        # --------------------------------------------------------------------- getImage

    @overload
    def getImage(self, *, fix: bool = True) -> np.ndarray: ...
    @overload
    def getImage(self, numChannel: int, *, fix: bool = True) -> np.ndarray: ...

    def getImage(
        self, numChannel: int | None = None, *, fix: bool = True
    ) -> np.ndarray:
        if self._py_camera() is None:  # pragma: no cover
            if numChannel is not None:
                return super().getImage(numChannel, fix=fix)
            return super().getImage(fix=fix)

        if self._current_image_buffer is None:
            raise RuntimeError(
                "No image buffer available. Call snapImage() before calling getImage()."
            )

        return self._current_image_buffer

    # ---------------------------------------------------------------- sequence common

    def _start_sequence(
        self, cam: CameraDevice, n_images: int | None, stop_on_overflow: bool
    ) -> None:
        """Initialise _seq state and call cam.start_sequence."""
        shape, dtype = cam.shape(), np.dtype(cam.dtype())
        camera_label = cam.get_label()

        n_components = shape[2] if len(shape) > 2 else 1
        base_meta: dict[str, Any] = {
            KW.Binning: cam.get_property_value(KW.Binning),
            KW.Metadata_CameraLabel: camera_label,
            KW.Metadata_Height: str(shape[0]),
            KW.Metadata_Width: str(shape[1]),
            KW.Metadata_ROI_X: "0",
            KW.Metadata_ROI_Y: "0",
            KW.PixelType: PixelType.for_bytes(dtype.itemsize, n_components),
        }

        def get_buffer_with_overflow_handling(
            shape: Sequence[int], dtype: DTypeLike
        ) -> np.ndarray:
            try:
                return self._seq_buffer.acquire_slot(shape, dtype)
            except BufferError:
                if not stop_on_overflow:  # we shouldn't get here...
                    raise  # pragma: no cover
                raise BufferOverflowStop() from None

        # Keep track of images acquired for metadata and auto-stop
        counter = count()

        # Create metadata-injecting wrapper for finalize callback
        def finalize_with_metadata(cam_meta: Mapping) -> None:
            img_number = next(counter)
            elapsed_ms = (perf_counter_ns() - start_time) / 1e6
            received = datetime.now().isoformat(sep=" ")
            self._seq_buffer.finalize_slot(
                {
                    **base_meta,
                    **cam_meta,
                    KW.Metadata_TimeInCore: received,
                    KW.Metadata_ImageNumber: str(img_number),
                    KW.Elapsed_Time_ms: f"{elapsed_ms:.2f}",
                }
            )

            # Auto-stop when we've acquired the requested number of images
            if n_images is not None and (img_number + 1) >= n_images:
                self._stop_event.set()

        # Reset the circular buffer and stop event -------------

        self._stop_event.clear()
        self._seq_buffer.clear()
        self._seq_buffer.overwrite_on_overflow = not stop_on_overflow

        # Create the Acquisition Thread ---------

        self._acquisition_thread = AcquisitionThread(
            image_generator=cam.start_sequence(
                n_images, get_buffer_with_overflow_handling
            ),
            finalize=finalize_with_metadata,
            label=camera_label,
            stop_event=self._stop_event,
        )

        # Zoom zoom ---------

        start_time = perf_counter_ns()
        self._acquisition_thread.start()

    # ------------------------------------------------- startSequenceAcquisition

    # startSequenceAcquisition
    def _do_start_sequence_acquisition(
        self, cameraLabel: str, numImages: int, intervalMs: float, stopOnOverflow: bool
    ) -> None:
        if (cam := self._py_camera(cameraLabel)) is None:  # pragma: no cover
            return pymmcore.CMMCore.startSequenceAcquisition(
                self, cameraLabel, numImages, intervalMs, stopOnOverflow
            )
        with cam:
            self._start_sequence(cam, numImages, stopOnOverflow)

    # ------------------------------------------------- continuous acquisition

    # startContinuousSequenceAcquisition
    def _do_start_continuous_sequence_acquisition(self, intervalMs: float = 0) -> None:
        if (cam := self._py_camera()) is None:  # pragma: no cover
            return pymmcore.CMMCore.startContinuousSequenceAcquisition(self, intervalMs)
        with cam:
            self._start_sequence(cam, None, False)

    # ---------------------------------------------------------------- stopSequence

    def _do_stop_sequence_acquisition(self, cameraLabel: str) -> None:
        if self._py_camera(cameraLabel) is None:  # pragma: no cover
            pymmcore.CMMCore.stopSequenceAcquisition(self, cameraLabel)

        if self._acquisition_thread is not None:
            self._stop_event.set()
            self._acquisition_thread.join()
            self._acquisition_thread = None

    # ------------------------------------------------------------------ queries
    @overload
    def isSequenceRunning(self) -> bool: ...
    @overload
    def isSequenceRunning(self, cameraLabel: DeviceLabel | str) -> bool: ...
    def isSequenceRunning(self, cameraLabel: DeviceLabel | str | None = None) -> bool:
        if self._py_camera(cameraLabel) is None:
            return super().isSequenceRunning()

        if self._acquisition_thread is None:
            return False

        # Check if the thread is actually still alive
        if not self._acquisition_thread.is_alive():
            # Thread has finished, clean it up
            self._acquisition_thread = None
            return False

        return True

    def getRemainingImageCount(self) -> int:
        if self._py_camera() is None:
            return super().getRemainingImageCount()
        return len(self._seq_buffer) if self._seq_buffer is not None else 0

    # ---------------------------------------------------- getImages

    def getLastImage(self, *, out: np.ndarray | None = None) -> np.ndarray:
        if self._py_camera() is None:
            return super().getLastImage()
        if (
            not (self._seq_buffer)
            or (result := self._seq_buffer.peek_last(out=out)) is None
        ):
            raise IndexError("Circular buffer is empty.")
        return result[0]

    @overload
    def getLastImageMD(
        self,
        channel: int,
        slice: int,
        md: pymmcore.Metadata,
        /,
        *,
        out: np.ndarray | None = None,
    ) -> np.ndarray: ...
    @overload
    def getLastImageMD(
        self, md: pymmcore.Metadata, /, *, out: np.ndarray | None = None
    ) -> np.ndarray: ...
    def getLastImageMD(self, *args: Any, out: np.ndarray | None = None) -> np.ndarray:
        if self._py_camera() is None:
            return super().getLastImageMD(*args)
        md_object = args[0] if len(args) == 1 else args[-1]
        if not isinstance(md_object, pymmcore.Metadata):  # pragma: no cover
            raise TypeError("Expected a Metadata object for the last argument.")

        if (
            not (self._seq_buffer)
            or (result := self._seq_buffer.peek_last(out=out)) is None
        ):
            raise IndexError("Circular buffer is empty.")

        img, md = result
        for k, v in md.items():
            tag = pymmcore.MetadataSingleTag(k, "_", False)
            tag.SetValue(str(v))
            md_object.SetTag(tag)

        return img

    def getNBeforeLastImageMD(
        self,
        n: int,
        md: pymmcore.Metadata,
        /,
        *,
        out: np.ndarray | None = None,
    ) -> np.ndarray:
        if self._py_camera() is None:
            return super().getNBeforeLastImageMD(n, md)

        if (
            not (self._seq_buffer)
            or (result := self._seq_buffer.peek_nth_from_last(n, out=out)) is None
        ):
            raise IndexError("Circular buffer is empty or n is out of range.")

        img, md_data = result
        for k, v in md_data.items():
            tag = pymmcore.MetadataSingleTag(k, "_", False)
            tag.SetValue(str(v))
            md.SetTag(tag)

        return img

    # ---------------------------------------------------- popNext

    def _pop_or_raise(self) -> tuple[np.ndarray, Mapping]:
        if not self._seq_buffer or (data := self._seq_buffer.pop_next()) is None:
            raise IndexError("Circular buffer is empty.")
        return data

    def popNextImage(self, *, fix: bool = True) -> np.ndarray:
        if self._py_camera() is None:
            return super().popNextImage(fix=fix)
        return self._pop_or_raise()[0]

    @overload
    def popNextImageMD(
        self, channel: int, slice: int, md: pymmcore.Metadata, /
    ) -> np.ndarray: ...
    @overload
    def popNextImageMD(self, md: pymmcore.Metadata, /) -> np.ndarray: ...
    def popNextImageMD(self, *args: Any) -> np.ndarray:
        if self._py_camera() is None:
            return super().popNextImageMD(*args)

        md_object = args[0] if len(args) == 1 else args[-1]
        if not isinstance(md_object, pymmcore.Metadata):  # pragma: no cover
            raise TypeError("Expected a Metadata object for the last argument.")

        img, md = self._pop_or_raise()
        for k, v in md.items():
            tag = pymmcore.MetadataSingleTag(k, "_", False)
            tag.SetValue(str(v))
            md_object.SetTag(tag)
        return img

    # ---------------------------------------------------------------- circular buffer

    def setCircularBufferMemoryFootprint(self, sizeMB: int) -> None:
        """Set the circular buffer memory footprint in MB."""
        if self._py_camera() is None:
            return super().setCircularBufferMemoryFootprint(sizeMB)

        if sizeMB <= 0:  # pragma: no cover
            raise ValueError("Buffer size must be greater than 0 MB")

        # TODO: what if sequence is running?
        if self.isSequenceRunning():
            self.stopSequenceAcquisition()

        self._seq_buffer = SequenceBuffer(size_mb=sizeMB)

    def initializeCircularBuffer(self) -> None:
        """Initialize the circular buffer."""
        if self._py_camera() is None:
            return super().initializeCircularBuffer()

        self._seq_buffer.clear()

    def getBufferFreeCapacity(self) -> int:
        """Get the number of free slots in the circular buffer."""
        if (cam := self._py_camera()) is None:
            return super().getBufferFreeCapacity()

        if (bytes_per_frame := self._predicted_bytes_per_frame(cam)) <= 0:
            return 0  # pragma: no cover  # Invalid frame size

        if (free_bytes := self._seq_buffer.free_bytes) <= 0:
            return 0

        return free_bytes // bytes_per_frame

    def getBufferTotalCapacity(self) -> int:
        """Get the total capacity of the circular buffer."""
        if (cam := self._py_camera()) is None:
            return super().getBufferTotalCapacity()

        if (bytes_per_frame := self._predicted_bytes_per_frame(cam)) <= 0:
            return 0  # pragma: no cover  # Invalid frame size

        return self._seq_buffer.size_bytes // bytes_per_frame

    def _predicted_bytes_per_frame(self, cam: CameraDevice) -> int:
        # Estimate capacity based on camera settings and circular buffer size
        shape, dtype = cam.shape(), np.dtype(cam.dtype())
        return int(np.prod(shape) * dtype.itemsize)

    def getCircularBufferMemoryFootprint(self) -> int:
        """Get the circular buffer memory footprint in MB."""
        if self._py_camera() is None:
            return super().getCircularBufferMemoryFootprint()

        return int(self._seq_buffer.size_mb)

    def clearCircularBuffer(self) -> None:
        """Clear all images from the circular buffer."""
        if self._py_camera() is None:
            return super().clearCircularBuffer()

        self._seq_buffer.clear()

    def isBufferOverflowed(self) -> bool:
        """Check if the circular buffer has overflowed."""
        if self._py_camera() is None:
            return super().isBufferOverflowed()

        return self._seq_buffer.overflow_occurred

    # ----------------------------------------------------------------- image info

    def getImageBitDepth(self) -> int:
        if (cam := self._py_camera()) is None:  # pragma: no cover
            return super().getImageBitDepth()
        dtype = np.dtype(cam.dtype())
        return dtype.itemsize * 8

    def getBytesPerPixel(self) -> int:
        if (cam := self._py_camera()) is None:  # pragma: no cover
            return super().getBytesPerPixel()
        dtype = np.dtype(cam.dtype())
        return dtype.itemsize

    def getImageBufferSize(self) -> int:
        if (cam := self._py_camera()) is None:  # pragma: no cover
            return super().getImageBufferSize()
        shape, dtype = cam.shape(), np.dtype(cam.dtype())
        return int(np.prod(shape) * dtype.itemsize)

    def getImageHeight(self) -> int:
        if (cam := self._py_camera()) is None:  # pragma: no cover
            return super().getImageHeight()
        return cam.shape()[0]

    def getImageWidth(self) -> int:
        if (cam := self._py_camera()) is None:  # pragma: no cover
            return super().getImageWidth()
        return cam.shape()[1]

    def getNumberOfComponents(self) -> int:
        if (cam := self._py_camera()) is None:  # pragma: no cover
            return super().getNumberOfComponents()
        shape = cam.shape()
        return 1 if len(shape) == 2 else shape[2]

    def getNumberOfCameraChannels(self) -> int:
        if self._py_camera() is None:  # pragma: no cover
            return super().getNumberOfCameraChannels()
        raise NotImplementedError(
            "getNumberOfCameraChannels is not implemented for Python cameras."
        )

    def getCameraChannelName(self, channelNr: int) -> str:
        """Get the name of the camera channel."""
        if self._py_camera() is None:  # pragma: no cover
            return super().getCameraChannelName(channelNr)
        raise NotImplementedError(
            "getCameraChannelName is not implemented for Python cameras."
        )

    @overload
    def getExposure(self) -> float: ...
    @overload
    def getExposure(self, cameraLabel: DeviceLabel | str, /) -> float: ...
    def getExposure(self, cameraLabel: DeviceLabel | str | None = None) -> float:
        """Get the exposure time in milliseconds."""
        if (cam := self._py_camera(cameraLabel)) is None:  # pragma: no cover
            if cameraLabel is None:
                return super().getExposure()
            return super().getExposure(cameraLabel)

        with cam:
            return cam.get_exposure()

    @overload
    def setExposure(self, exp: float, /) -> None: ...
    @overload
    def setExposure(self, cameraLabel: DeviceLabel | str, dExp: float, /) -> None: ...
    def setExposure(self, *args: Any) -> None:
        """Set the exposure time in milliseconds."""
        label, args = _ensure_label(args, min_args=2, getter=self.getCameraDevice)
        if (cam := self._py_camera(label)) is None:  # pragma: no cover
            return super().setExposure(label, *args)
        with cam:
            cam.set_exposure(*args)

    def _do_set_roi(self, label: str, x: int, y: int, width: int, height: int) -> None:
        if self._py_camera(label) is not None:
            raise NotImplementedError(
                "setROI is not yet implemented for Python cameras."
            )
        return pymmcore.CMMCore.setROI(self, label, x, y, width, height)

    @overload
    def getROI(self) -> list[int]: ...
    @overload
    def getROI(self, label: DeviceLabel | str) -> list[int]: ...
    def getROI(self, label: DeviceLabel | str = "") -> list[int]:
        """Get the current region of interest (ROI) for the camera."""
        if self._py_camera(label) is None:  # pragma: no cover
            raise NotImplementedError(
                "getROI is not yet implemented for Python cameras."
            )
        return super().getROI(label)

    def clearROI(self) -> None:
        """Clear the current region of interest (ROI) for the camera."""
        if self._py_camera() is not None:  # pragma: no cover
            raise NotImplementedError(
                "clearROI is not yet implemented for Python cameras."
            )
        return super().clearROI()

    def isExposureSequenceable(self, cameraLabel: DeviceLabel | str) -> bool:
        """Check if the camera supports exposure sequences."""
        if (cam := self._py_camera(cameraLabel)) is None:  # pragma: no cover
            return super().isExposureSequenceable(cameraLabel)
        with cam:
            return cam.is_property_sequenceable(KW.Exposure)

    def loadExposureSequence(
        self, cameraLabel: DeviceLabel | str, exposureSequence_ms: Sequence[float]
    ) -> None:
        """Transfer a sequence of exposure times to the camera."""
        if (cam := self._py_camera(cameraLabel)) is None:  # pragma: no cover
            return super().loadExposureSequence(cameraLabel, exposureSequence_ms)
        with cam:
            cam.load_property_sequence(KW.Exposure, exposureSequence_ms)

    def getExposureSequenceMaxLength(self, cameraLabel: DeviceLabel | str) -> int:
        """Get the maximum length of the exposure sequence."""
        if (cam := self._py_camera(cameraLabel)) is None:  # pragma: no cover
            return super().getExposureSequenceMaxLength(cameraLabel)
        with cam:
            return cam.get_property_info(KW.Exposure).sequence_max_length

    def startExposureSequence(self, cameraLabel: DeviceLabel | str) -> None:
        """Start a sequence of exposures."""
        if (cam := self._py_camera(cameraLabel)) is None:  # pragma: no cover
            return super().startExposureSequence(cameraLabel)
        with cam:
            cam.start_property_sequence(KW.Exposure)

    def stopExposureSequence(self, cameraLabel: DeviceLabel | str) -> None:
        """Stop a sequence of exposures."""
        if (cam := self._py_camera(cameraLabel)) is None:  # pragma: no cover
            return super().stopExposureSequence(cameraLabel)
        with cam:
            cam.stop_property_sequence(KW.Exposure)

    def prepareSequenceAcquisition(self, cameraLabel: DeviceLabel | str) -> None:
        """Prepare the camera for sequence acquisition."""
        if self._py_camera(cameraLabel) is None:  # pragma: no cover
            return super().prepareSequenceAcquisition(cameraLabel)
        # TODO: Implement prepareSequenceAcquisition for Python cameras?

    @overload
    def getPixelSizeAffine(self) -> AffineTuple: ...
    @overload
    def getPixelSizeAffine(self, cached: bool, /) -> AffineTuple: ...
    def getPixelSizeAffine(self, cached: bool = False) -> AffineTuple:
        """Get the pixel size affine transformation matrix."""
        if not (res_id := self.getCurrentPixelSizeConfig(cached)):  # pragma: no cover
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)  # null affine

        cam = self._py_camera()
        if cam is not None:
            with cam:
                binning = float(cam.get_property_value(KW.Binning))
        else:
            binning = 1.0
        if cam is None or binning == 1:
            return tuple(super().getPixelSizeAffine(cached))  # type: ignore

        # in CMMCore, they scale the pixel size affine by the binning factor and mag
        # but they won't pay attention to our camera so we have to reimplement it here
        af = self.getPixelSizeAffineByID(res_id)
        if (factor := binning / self.getMagnificationFactor()) != 1.0:
            af = cast("AffineTuple", tuple(v * factor for v in af))
        return af

    @overload
    def getPixelSizeUm(self) -> float: ...
    @overload
    def getPixelSizeUm(self, cached: bool) -> float: ...
    def getPixelSizeUm(self, cached: bool = False) -> float:
        """Get the pixel size in micrometers."""
        if not (res_id := self.getCurrentPixelSizeConfig(cached)):  # pragma: no cover
            return 0.0

        # in CMMCore, they scale the pixel size by the binning factor and mag
        # but they won't pay attention to our camera so we have to reimplement it here
        cam = self._py_camera()
        if cam is None or (binning := float(cam.get_property_value(KW.Binning))) == 1:
            return super().getPixelSizeUm(cached)

        return self.getPixelSizeUmByID(res_id) * binning / self.getMagnificationFactor()

    # ########################################################################
    # ------------------------- SLM Device Methods -------------------------
    # ########################################################################

    # --------------------------------------------------------------------- utils

    def _py_slm(self, slmLabel: str | None = None) -> SLMDevice | None:
        """Return the *Python* SLM for ``label`` (or current), else ``None``."""
        label = slmLabel or self.getSLMDevice()
        if label in self._pydevices:
            return self._pydevices.get_device_of_type(label, SLMDevice)
        return None  # pragma: no cover

    def setSLMDevice(self, slmLabel: DeviceLabel | str) -> None:
        """Set the SLM device."""
        label = self._set_current_if_pydevice(KW.CoreSLM, slmLabel)
        super().setSLMDevice(label)

    def getSLMDevice(self) -> DeviceLabel | Literal[""]:
        """Returns the label of the currently selected SLM device.

        Returns empty string if no SLM device is selected.
        """
        return self._pycore.current(KW.CoreSLM) or super().getSLMDevice()

    # ------------------------------------------------------------------- set image

    @overload
    def setSLMImage(self, pixels: np.ndarray, /) -> None: ...
    @overload
    def setSLMImage(
        self, slmLabel: DeviceLabel | str, pixels: np.ndarray, /
    ) -> None: ...
    def setSLMImage(self, *args: Any) -> None:
        """Load the image into the SLM device adapter."""
        label, args = _ensure_label(args, min_args=2, getter=self.getSLMDevice)
        if (slm := self._py_slm(label)) is None:  # pragma: no cover
            return super().setSLMImage(label, *args)

        with slm:
            shape, dtype = slm.shape(), np.dtype(slm.dtype())
            arr = np.asarray(args[0], dtype=dtype)
            if not arr.shape == shape:  # pragma: no cover
                raise ValueError(
                    f"Image shape {arr.shape} doesn't match SLM shape {shape}."
                )
            slm.set_image(arr)

    def getSLMImage(self, slmLabel: DeviceLabel | str | None = None) -> np.ndarray:
        """Get the current image from the SLM device."""
        if (slm := self._py_slm(slmLabel)) is None:
            raise NotImplementedError(
                "getSLMImage is not implemented for C++ SLM devices. "
                "(This method is unique to Python SLM devices.)"
            )

        with slm:
            return slm.get_image()

    @overload
    def setSLMPixelsTo(self, intensity: int, /) -> None: ...
    @overload
    def setSLMPixelsTo(self, red: int, green: int, blue: int, /) -> None: ...
    @overload
    def setSLMPixelsTo(
        self, slmLabel: DeviceLabel | str, intensity: int, /
    ) -> None: ...
    @overload
    def setSLMPixelsTo(
        self, slmLabel: DeviceLabel | str, red: int, green: int, blue: int, /
    ) -> None: ...
    def setSLMPixelsTo(self, *args: Any) -> None:
        """Set all pixels of the SLM to a uniform intensity or RGB values."""
        if len(args) < 1 or len(args) > 4:  # pragma: no cover
            raise ValueError("setSLMPixelsTo requires 1 to 4 arguments.")

        label = args[0] if len(args) in (2, 4) else self.getSLMDevice()
        if (slm := self._py_slm(label)) is None:  # pragma: no cover
            return super().setSLMPixelsTo(*args)

        with slm:
            shape = slm.shape()
            dtype = slm.dtype()

            # Determine if we have RGB (3 or 4 args) or single intensity (1 or 2 args)
            if len(args) == 1:  # setSLMPixelsTo(intensity)
                pixels = np.full(shape, args[0], dtype=dtype)
            elif len(args) == 2:  # setSLMPixelsTo(slmLabel, intensity)
                pixels = np.full(shape, args[1], dtype=dtype)
            elif len(args) == 3:  # setSLMPixelsTo(red, green, blue)
                rgb_values = args
                pixels = np.broadcast_to(rgb_values, (*shape[:2], 3))
            elif len(args) == 4:  # setSLMPixelsTo(slmLabel, red, green, blue)
                rgb_values = args[1:4]
                pixels = np.broadcast_to(rgb_values, (*shape[:2], 3))
            if len(shape) == 2 and pixels.ndim == 3:
                # Grayscale SLM - convert RGB to grayscale (simple average)
                pixels = np.mean(pixels, axis=2, dtype=dtype).astype(dtype)

            slm.set_image(pixels)

    @overload
    def displaySLMImage(self) -> None: ...
    @overload
    def displaySLMImage(self, slmLabel: DeviceLabel | str, /) -> None: ...
    def displaySLMImage(self, slmLabel: DeviceLabel | str | None = None) -> None:
        """Command the SLM to display the loaded image."""
        label = slmLabel or self.getSLMDevice()
        if (slm := self._py_slm(label)) is None:  # pragma: no cover
            if slmLabel is None:
                return super().displaySLMImage(label)
            return super().displaySLMImage(slmLabel)

        with slm:
            slm.display_image()

    # ------------------------------------------------------------------ exposure

    @overload
    def setSLMExposure(self, interval_ms: float, /) -> None: ...
    @overload
    def setSLMExposure(
        self, slmLabel: DeviceLabel | str, interval_ms: float, /
    ) -> None: ...
    def setSLMExposure(self, *args: Any) -> None:
        """Command the SLM to turn off after a specified interval."""
        label, args = _ensure_label(args, min_args=2, getter=self.getSLMDevice)
        if (slm := self._py_slm(label)) is None:  # pragma: no cover
            return super().setSLMExposure(label, *args)

        with slm:
            slm.set_exposure(args[0])

    @overload
    def getSLMExposure(self) -> float: ...
    @overload
    def getSLMExposure(self, slmLabel: DeviceLabel | str, /) -> float: ...
    def getSLMExposure(self, slmLabel: DeviceLabel | str | None = None) -> float:
        """Find out the exposure interval of an SLM."""
        if (slm := self._py_slm(slmLabel)) is None:  # pragma: no cover
            label = slmLabel or self.getSLMDevice()
            return super().getSLMExposure(label)

        with slm:
            return slm.get_exposure()

    # ----------------------------------------------------------------- dimensions

    @overload
    def getSLMWidth(self) -> int: ...
    @overload
    def getSLMWidth(self, slmLabel: DeviceLabel | str, /) -> int: ...
    def getSLMWidth(self, slmLabel: DeviceLabel | str | None = None) -> int:
        """Returns the width of the SLM in pixels."""
        if (slm := self._py_slm(slmLabel)) is None:  # pragma: no cover
            label = slmLabel or self.getSLMDevice()
            return super().getSLMWidth(label)

        with slm:
            return slm.shape()[1]  # width is second dimension

    @overload
    def getSLMHeight(self) -> int: ...
    @overload
    def getSLMHeight(self, slmLabel: DeviceLabel | str, /) -> int: ...
    def getSLMHeight(self, slmLabel: DeviceLabel | str | None = None) -> int:
        """Returns the height of the SLM in pixels."""
        if (slm := self._py_slm(slmLabel)) is None:  # pragma: no cover
            label = slmLabel or self.getSLMDevice()
            return super().getSLMHeight(label)

        with slm:
            return slm.shape()[0]  # height is first dimension

    @overload
    def getSLMNumberOfComponents(self) -> int: ...
    @overload
    def getSLMNumberOfComponents(self, slmLabel: DeviceLabel | str, /) -> int: ...
    def getSLMNumberOfComponents(
        self, slmLabel: DeviceLabel | str | None = None
    ) -> int:
        """Returns the number of color components (channels) in the SLM."""
        if (slm := self._py_slm(slmLabel)) is None:  # pragma: no cover
            label = slmLabel or self.getSLMDevice()
            return super().getSLMNumberOfComponents(label)

        with slm:
            shape = slm.shape()
            return 1 if len(shape) == 2 else shape[2]

    @overload
    def getSLMBytesPerPixel(self) -> int: ...
    @overload
    def getSLMBytesPerPixel(self, slmLabel: DeviceLabel | str, /) -> int: ...
    def getSLMBytesPerPixel(self, slmLabel: DeviceLabel | str | None = None) -> int:
        """Returns the number of bytes per pixel for the SLM."""
        if (slm := self._py_slm(slmLabel)) is None:  # pragma: no cover
            label = slmLabel or self.getSLMDevice()
            return super().getSLMBytesPerPixel(label)

        with slm:
            dtype = np.dtype(slm.dtype())
            return dtype.itemsize

    # ------------------------------------------------------------------ sequences

    def getSLMSequenceMaxLength(self, slmLabel: DeviceLabel | str) -> int:
        """Get the maximum length of an image sequence that can be uploaded."""
        if (slm := self._py_slm(slmLabel)) is None:  # pragma: no cover
            return super().getSLMSequenceMaxLength(slmLabel)

        with slm:
            return slm.get_sequence_max_length()

    def loadSLMSequence(
        self,
        slmLabel: DeviceLabel | str,
        imageSequence: Sequence[bytes | np.ndarray],
    ) -> None:
        """Load a sequence of images to the SLM."""
        if (slm := self._py_slm(slmLabel)) is None:  # pragma: no cover
            return super().loadSLMSequence(slmLabel, imageSequence)  # type: ignore[arg-type]

        with slm:
            if (m := slm.get_sequence_max_length()) == 0:
                raise RuntimeError(f"SLM {slmLabel!r} does not support sequences.")

            shape = slm.shape()
            dtype = np.dtype(slm.dtype())

            np_arrays: list[np.ndarray] = []
            for i, img_bytes in enumerate(imageSequence):
                if isinstance(img_bytes, bytes):
                    arr = np.frombuffer(img_bytes, dtype=dtype).reshape(shape)
                else:
                    arr = np.asarray(img_bytes, dtype=dtype)
                    if arr.shape != shape:
                        raise ValueError(
                            f"Image {i} shape {arr.shape} does not "
                            f"match SLM shape {shape}"
                        )
                np_arrays.append(arr)
            if len(np_arrays) > (m := slm.get_sequence_max_length()):
                raise ValueError(
                    f"Sequence length {len(np_arrays)} exceeds maximum {m}."
                )
            slm.send_sequence(np_arrays)

    def startSLMSequence(self, slmLabel: DeviceLabel | str) -> None:
        """Start a sequence of images on the SLM."""
        if (slm := self._py_slm(slmLabel)) is None:  # pragma: no cover
            return super().startSLMSequence(slmLabel)

        with slm:
            slm.start_sequence()

    def stopSLMSequence(self, slmLabel: DeviceLabel | str) -> None:
        """Stop a sequence of images on the SLM."""
        if (slm := self._py_slm(slmLabel)) is None:  # pragma: no cover
            return super().stopSLMSequence(slmLabel)

        with slm:
            slm.stop_sequence()

    # ########################################################################
    # ------------------------ State Device Methods -------------------------
    # ########################################################################

    # --------------------------------------------------------------------- utils

    def _py_state(self, stateLabel: str | None = None) -> StateDevice | None:
        """Return the *Python* State device for ``label``, else ``None``."""
        label = stateLabel or ""
        if label in self._pydevices:
            return self._pydevices.get_device_of_type(label, StateDevice)
        return None  # pragma: no cover

    # ------------------------------------------------------------------- setState

    def setState(self, stateDeviceLabel: DeviceLabel | str, state: int) -> None:
        """Set state (position) on the specific device."""
        if (state_dev := self._py_state(stateDeviceLabel)) is None:  # pragma: no cover
            return super().setState(stateDeviceLabel, state)

        with state_dev:
            state_dev.set_position_or_label(state)
            # keep cache in sync
            try:
                self._cache_set(
                    stateDeviceLabel,
                    KW.State,
                    int(state_dev.get_property_value(KW.State)),
                )
            except Exception:
                pass
            try:
                self._cache_set(
                    stateDeviceLabel, KW.Label, state_dev.get_property_value(KW.Label)
                )
            except Exception:
                pass

    # ------------------------------------------------------------------- getState

    def getState(self, stateDeviceLabel: DeviceLabel | str) -> int:
        """Return the current state (position) on the specific device."""
        if (state_dev := self._py_state(stateDeviceLabel)) is None:  # pragma: no cover
            return super().getState(stateDeviceLabel)

        with state_dev:
            return int(state_dev.get_property_value(KW.State))

    # ---------------------------------------------------------------- getNumberOfStates

    def getNumberOfStates(self, stateDeviceLabel: DeviceLabel | str) -> int:
        """Return the total number of available positions (states)."""
        if (state_dev := self._py_state(stateDeviceLabel)) is None:  # pragma: no cover
            return super().getNumberOfStates(stateDeviceLabel)

        with state_dev:
            return state_dev.get_property_info(KW.State).number_of_allowed_values

    # ----------------------------------------------------------------- setStateLabel

    def setStateLabel(
        self, stateDeviceLabel: DeviceLabel | str, stateLabel: str
    ) -> None:
        """Set device state using the previously assigned label (string)."""
        if (state_dev := self._py_state(stateDeviceLabel)) is None:  # pragma: no cover
            return super().setStateLabel(stateDeviceLabel, stateLabel)

        with state_dev:
            try:
                state_dev.set_position_or_label(stateLabel)
                # keep cache in sync
                try:
                    self._cache_set(
                        stateDeviceLabel,
                        KW.Label,
                        state_dev.get_property_value(KW.Label),
                    )
                except Exception:
                    pass
                try:
                    self._cache_set(
                        stateDeviceLabel,
                        KW.State,
                        int(state_dev.get_property_value(KW.State)),
                    )
                except Exception:
                    pass
            except KeyError as e:
                raise RuntimeError(str(e)) from e  # convert to RuntimeError

    # ----------------------------------------------------------------- getStateLabel

    def getStateLabel(self, stateDeviceLabel: DeviceLabel | str) -> StateLabel:
        """Return the current state as the label (string)."""
        if (state_dev := self._py_state(stateDeviceLabel)) is None:  # pragma: no cover
            return super().getStateLabel(stateDeviceLabel)

        with state_dev:
            return cast("StateLabel", state_dev.get_property_value(KW.Label))

    # --------------------------------------------------------------- defineStateLabel

    def defineStateLabel(
        self, stateDeviceLabel: DeviceLabel | str, state: int, label: str
    ) -> None:
        """Define a label for the specific state."""
        if (state_dev := self._py_state(stateDeviceLabel)) is None:  # pragma: no cover
            return super().defineStateLabel(stateDeviceLabel, state, label)

        with state_dev:
            state_dev.assign_label_to_position(state, label)

    # ----------------------------------------------------------------- getStateLabels

    def getStateLabels(
        self, stateDeviceLabel: DeviceLabel | str
    ) -> tuple[StateLabel, ...]:
        """Return labels for all states."""
        if (state_dev := self._py_state(stateDeviceLabel)) is None:  # pragma: no cover
            return super().getStateLabels(stateDeviceLabel)

        with state_dev:
            return tuple(state_dev.get_property_info(KW.Label).allowed_values or [])

    # ------------------------------------------------------------- getStateFromLabel

    def getStateFromLabel(
        self, stateDeviceLabel: DeviceLabel | str, stateLabel: str
    ) -> int:
        """Obtain the state for a given label."""
        if (state_dev := self._py_state(stateDeviceLabel)) is None:  # pragma: no cover
            return super().getStateFromLabel(stateDeviceLabel, stateLabel)

        with state_dev:
            try:
                return state_dev.get_position_for_label(stateLabel)
            except KeyError as e:
                raise RuntimeError(str(e)) from e  # convert to RuntimeError

    # ########################################################################
    # ------------------------ Shutter Device Methods ------------------------
    # ########################################################################

    def _py_shutter(self, shutterLabel: str | None = None) -> ShutterDevice | None:
        """Return the *Python* Shutter device for ``label``, else ``None``."""
        label = shutterLabel or self.getShutterDevice()
        if label in self._pydevices:
            return self._pydevices.get_device_of_type(label, ShutterDevice)
        return None

    def setShutterDevice(self, shutterLabel: DeviceLabel | str) -> None:
        label = self._set_current_if_pydevice(KW.CoreShutter, shutterLabel)
        super().setShutterDevice(label)

    def getShutterDevice(self) -> DeviceLabel | Literal[""]:
        """Returns the label of the currently selected Shutter device.

        Returns empty string if no Shutter device is selected.
        """
        return self._pycore.current(KW.CoreShutter) or super().getShutterDevice()

    @overload
    def getShutterOpen(self) -> bool: ...
    @overload
    def getShutterOpen(self, shutterLabel: DeviceLabel | str) -> bool: ...
    def getShutterOpen(self, shutterLabel: DeviceLabel | str | None = None) -> bool:
        shutterLabel = shutterLabel or self.getShutterDevice()
        if (shutter := self._py_shutter(shutterLabel)) is None:
            return super().getShutterOpen(shutterLabel)

        with shutter:
            return shutter.get_open()

    def _do_shutter_open(self, shutterLabel: str, state: bool, /) -> None:
        """Open or close the shutter."""
        if (shutter := self._py_shutter(shutterLabel)) is None:  # pragma: no cover
            return pymmcore.CMMCore.setShutterOpen(self, shutterLabel, state)

        with shutter:
            shutter.set_open(state)


# -------------------------------------------------------------------------------


def _ensure_label(
    args: tuple[_T, ...], min_args: int, getter: Callable[[], str]
) -> tuple[str, tuple[_T, ...]]:
    """Ensure we have a device label.

    Designed to be used with overloaded methods that MAY take a device label as the
    first argument.

    If the number of arguments is less than `min_args`, the label is obtained from the
    getter function. If the number of arguments is greater than or equal to `min_args`,
    the label is the first argument and the remaining arguments are returned as a tuple
    """
    if len(args) < min_args:
        # we didn't get the label
        return getter(), args
    return cast("str", args[0]), args[1:]


class PropertyStateCache(MutableMapping[tuple[str, str], Any]):
    """A thread-safe cache for property states.

    Keys are tuples of (device_label, property_name), and values are the last known
    value of that property.
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], Any] = {}
        self._lock = threading.Lock()

    def __getitem__(self, key: tuple[str, str]) -> Any:
        with self._lock:
            try:
                return self._store[key]
            except KeyError:  # pragma: no cover
                prop, dev = key
                raise KeyError(
                    f"Property {prop!r} of device {dev!r} not found in cache"
                ) from None

    def __setitem__(self, key: tuple[str, str], value: Any) -> None:
        with self._lock:
            self._store[key] = value

    def __delitem__(self, key: tuple[str, str]) -> None:
        with self._lock:
            del self._store[key]

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._store

    def __iter__(self) -> Iterator[tuple[str, str]]:
        with self._lock:
            return iter(self._store.copy())  # Prevent modifications during iteration

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def __repr__(self) -> str:
        with self._lock:
            return f"{self.__class__.__name__}({self._store!r})"


# Threading ------------------------------------------------------


class AcquisitionThread(threading.Thread):
    """A thread for running sequence acquisition in the background."""

    def __init__(
        self,
        image_generator: Iterator[Mapping],
        finalize: Callable[[Mapping], None],
        label: str,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True)
        self.image_iterator = image_generator
        self.finalize = finalize
        self.label = label
        self.stop_event = stop_event

    def run(self) -> None:
        """Run the sequence and handle the generator pattern."""
        try:
            for metadata in self.image_iterator:
                self.finalize(metadata)
                if self.stop_event.is_set():
                    break
        except BufferOverflowStop:
            # Buffer overflow is a graceful stop condition, not an error
            # this was likely raised by the Unicore above in _start_sequence
            pass
        except BufferError:
            raise  # pragma: no cover
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                f"Error in device {self.label!r} during sequence acquisition: {e}"
            ) from e


# -------------------------------------------------------------------------------
