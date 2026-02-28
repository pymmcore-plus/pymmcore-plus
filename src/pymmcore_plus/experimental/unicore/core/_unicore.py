from __future__ import annotations

import os
import threading
import warnings
import weakref
from collections.abc import Callable, Iterator, MutableMapping, Sequence
from contextlib import suppress
from datetime import datetime
from itertools import count
from pathlib import Path
from time import perf_counter_ns
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
    overload,
)

import numpy as np
from typing_extensions import deprecated

import pymmcore_plus._pymmcore as pymmcore
from pymmcore_plus.core import CMMCorePlus, DeviceType, FocusDirection, Keyword
from pymmcore_plus.core import Keyword as KW
from pymmcore_plus.core._config import Configuration
from pymmcore_plus.core._constants import PixelType
from pymmcore_plus.experimental.unicore._device_manager import PyDeviceManager
from pymmcore_plus.experimental.unicore._proxy import create_core_proxy
from pymmcore_plus.experimental.unicore.devices._camera import CameraDevice
from pymmcore_plus.experimental.unicore.devices._device_base import Device
from pymmcore_plus.experimental.unicore.devices._hub import HubDevice
from pymmcore_plus.experimental.unicore.devices._shutter import ShutterDevice
from pymmcore_plus.experimental.unicore.devices._slm import SLMDevice
from pymmcore_plus.experimental.unicore.devices._stage import (
    StageDevice,
    XYStageDevice,
    _BaseStage,
)
from pymmcore_plus.experimental.unicore.devices._state import StateDevice

from ._config import load_system_configuration, save_system_configuration
from ._sequence_buffer import SequenceBuffer

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from typing import Literal, NewType, TypeAlias

    from numpy.typing import DTypeLike
    from pymmcore import (
        AdapterName,
        AffineTuple,
        ConfigPresetName,
        DeviceLabel,
        DeviceName,
        PropertyName,
        StateLabel,
    )

    from pymmcore_plus.core._constants import DeviceInitializationState, PropertyType

    PyDeviceLabel = NewType("PyDeviceLabel", DeviceLabel)
    _T = TypeVar("_T")

    # =============================================================================
    # Config Group Type Aliases
    # =============================================================================

    DevPropTuple = tuple[str, str]
    ConfigDict: TypeAlias = "MutableMapping[DevPropTuple, Any]"
    ConfigGroup: TypeAlias = "MutableMapping[ConfigPresetName, ConfigDict]"
    # technically the keys are ConfigGroupName (a NewType from pymmcore)
    # but to avoid all the casting, we use str here
    ConfigGroups: TypeAlias = MutableMapping[str, ConfigGroup]


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


class _CoreDevice:
    """A virtual core device.

    This mirrors the pattern used in CMMCore, where there is a virtual "core" device
    that maintains state about various "current" (real) devices.  When a call is made to
    `setSomeThing()` without specifying a device label, the CoreDevice is used to
    determine which real device to use.
    """

    def __init__(self, state_cache: ThreadSafeConfig) -> None:
        self._state_cache = state_cache
        self._pycurrent: dict[Keyword, PyDeviceLabel | None] = {}
        self.reset_current()

    def reset_current(self) -> None:
        """Set all current device labels to None."""
        self._pycurrent.update(CURRENT)

    def current(self, keyword: Keyword) -> PyDeviceLabel | None:
        """Return the current device label for the given keyword, or None if not set."""
        return self._pycurrent[keyword]

    def set_current(self, keyword: Keyword, label: str | None) -> None:
        """Set the current device label for the given keyword.

        If label is None, current is cleared (set to None).
        If label is a string, it is set as the current device for the keyword.
        """
        self._pycurrent[keyword] = cast("PyDeviceLabel", label)
        self._state_cache[(KW.CoreDevice, keyword)] = label


_DEFAULT_BUFFER_SIZE_MB: int = 1024
if buf := os.getenv("UNICORE_BUFFER_SIZE_MB"):
    try:
        _DEFAULT_BUFFER_SIZE_MB = int(buf)
    except ValueError:
        warnings.warn(
            f"Invalid value for UNICORE_BUFFER_SIZE_MB: {buf!r}. "
            f"Using default buffer size. {_DEFAULT_BUFFER_SIZE_MB} MB",
            stacklevel=2,
        )
elif os.getenv("CI") or os.getenv("PYTEST_VERSION"):
    _DEFAULT_BUFFER_SIZE_MB = 250


class UniMMCore(CMMCorePlus):
    """Unified Core object that first checks for python, then C++ devices."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._pydevices = PyDeviceManager()  # manager for python devices
        self._state_cache = ThreadSafeConfig()  # threadsafe cache for property states
        self._pycore = _CoreDevice(self._state_cache)  # virtual core for python
        self._stop_event: threading.Event = threading.Event()
        self._acquisition_thread: AcquisitionThread | None = None  # TODO: implement
        self._seq_buffer = SequenceBuffer(size_mb=_DEFAULT_BUFFER_SIZE_MB)
        # Storage for Python device settings in config groups.
        # Groups and presets are ALWAYS also created in C++ (via super() calls).
        # This dict only stores (device, property) -> value for Python devices.
        self._py_config_groups: ConfigGroups = {}

        super().__init__(*args, **kwargs)

        # Ensure Python-side state is cleaned up before ~CMMCore() runs,
        # since the C++ destructor calls CMMCore::reset() (not the Python
        # override), bypassing all Python cleanup.
        # NOTE: we pass individual objects (not self.__dict__) to avoid
        # preventing GC — __dict__ contains objects that reference self.
        weakref.finalize(
            self,
            UniMMCore._cleanup_python_state,
            self._stop_event,
            self._seq_buffer,
            self._pydevices,
            self._pycore,
            self._py_config_groups,
            self._state_cache,
        )

    @staticmethod
    def _cleanup_python_state(
        stop_event: threading.Event,
        seq_buffer: SequenceBuffer,
        pydevices: PyDeviceManager,
        pycore: _CoreDevice,
        py_config_groups: ConfigGroups,
        state_cache: ThreadSafeConfig,
    ) -> None:
        """Clean up all Python-side state (threads, buffers, devices)."""
        stop_event.set()
        seq_buffer.clear()
        pydevices.unload_all()
        pycore.reset_current()
        py_config_groups.clear()
        state_cache.clear()

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
        self._cleanup_python_state(
            self._stop_event,
            self._seq_buffer,
            self._pydevices,
            self._pycore,
            self._py_config_groups,
            self._state_cache,
        )
        super().reset()  # Clears C++ config groups, channel group, and devices

    def loadSystemConfiguration(
        self, fileName: str | Path = "MMConfig_demo.cfg"
    ) -> None:
        """Load a system config file conforming to the MM `.cfg` format.

        This is a Python implementation that supports both C++ and Python devices.
        Lines prefixed with `#py ` are processed as Python device commands but
        are ignored by upstream C++/pymmcore implementations.

        Format example::

            # C++ devices
            Device, Camera, DemoCamera, DCam
            Property, Core, Initialize, 1

            # Python devices (hidden from upstream via comment prefix)
            # py pyDevice,PyCamera,mypackage.cameras,MyCameraClass
            # py Property,PyCamera,Exposure,50.0

        https://micro-manager.org/Micro-Manager_Configuration_Guide#configuration-file-syntax

        For relative paths, the current working directory is first checked, then
        the device adapter path is checked.

        Parameters
        ----------
        fileName : str | Path
            Path to the configuration file. Defaults to "MMConfig_demo.cfg".
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
            # On failure, unload all devices to avoid leaving loaded but
            # uninitialized devices that could cause crashes
            with suppress(Exception):
                self.unloadAllDevices()
            raise

        self._last_sys_config = cfg_path
        # Emit system configuration loaded event
        self.events.systemConfigurationLoaded.emit()

    def saveSystemConfiguration(
        self, filename: str | Path, *, prefix_py_devices: bool = True
    ) -> None:
        """Save the current system configuration to a text file.

        This saves both C++ and Python devices.  Python device lines are prefixed
        with `#py ` by default so they are ignored by upstream C++/pymmcore.

        Parameters
        ----------
        filename : str | Path
            Path to save the configuration file.
        prefix_py_devices : bool, optional
            If True (default), Python device lines are prefixed with `#py ` so
            they are ignored by upstream C++/pymmcore implementations, allowing
            config files to work with regular pymmcore. If False, Python device
            lines are saved without the prefix (config will only be loadable by
            UniMMCore).
        """
        save_system_configuration(self, filename, prefix_py_devices=prefix_py_devices)

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
            if moduleName not in super().getDeviceAdapterNames():
                pydev = self._get_py_device_instance(moduleName, deviceName)
                self.loadPyDevice(label, pydev)
                return
            # it was a C++ device, should have worked ... raise the error
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

    def isPyDevice(self, label: DeviceLabel | str) -> bool:
        """Returns True if the specified device label corresponds to a Python device."""
        return label in self._pydevices

    def _cleanup_sequence_state(self, only_label: str | None = None) -> None:
        """Stop and clean up python-side sequence acquisition threads and state.

        if `only_label` is provided, only clean up state associated with that device
        label, otherwise clean up any/all sequence state.
        """
        if (
            only_label is not None
            and self._acquisition_thread is not None
            and self._acquisition_thread.label != only_label
        ):
            return

        self._stop_acquisition_thread()
        self._stop_event.clear()
        self._seq_buffer.clear()
        self._current_image_buffer = None

    def _cleanup_pydevice_state(self, label: str) -> None:
        """Clean UniCore-managed state associated with one unloaded py-device."""
        for keyword in CURRENT:
            if self._pycore.current(keyword) == label:
                self._pycore.set_current(keyword, None)

        self._state_cache.clear_device(label)

        for group_name, group in list(self._py_config_groups.items()):
            for preset_name, config in list(group.items()):
                to_clear = [k for k in config if k[0] == label]
                for key in to_clear:
                    config.pop(key, None)
                if not config:
                    group.pop(preset_name, None)
            if not group:
                self._py_config_groups.pop(group_name, None)

    def unloadDevice(self, label: DeviceLabel | str) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().unloadDevice(label)
        self._cleanup_sequence_state(label)
        self._pydevices.unload(label)
        self._cleanup_pydevice_state(label)

    def unloadAllDevices(self) -> None:
        self._cleanup_python_state(
            self._stop_event,
            self._seq_buffer,
            self._pydevices,
            self._pycore,
            self._py_config_groups,
            self._state_cache,
        )
        super().unloadAllDevices()

    def initializeDevice(self, label: DeviceLabel | str) -> None:
        if label not in self._pydevices:  # pragma: no cover
            return super().initializeDevice(label)
        return self._pydevices.initialize(label)

    def initializeAllDevices(self) -> None:
        super().initializeAllDevices()
        return self._pydevices.initialize_all()

    def getDeviceInitializationState(self, label: str) -> DeviceInitializationState:
        if label not in self._pydevices:  # pragma: no cover
            return super().getDeviceInitializationState(label)
        return self._pydevices.get_initialization_state(label)

    def getLoadedDevices(self) -> tuple[DeviceLabel, ...]:
        return tuple(self._pydevices) + tuple(super().getLoadedDevices())

    def getLoadedDevicesOfType(self, devType: int) -> tuple[DeviceLabel, ...]:
        pydevs = self._pydevices.get_labels_of_type(devType)
        return pydevs + tuple(super().getLoadedDevicesOfType(devType))

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

    # ---------------------------- Parent/Hub Relationships ---------------------------

    def getParentLabel(
        self, peripheralLabel: DeviceLabel | str
    ) -> DeviceLabel | Literal[""]:
        if peripheralLabel not in self._pydevices:  # pragma: no cover
            return super().getParentLabel(peripheralLabel)
        return self._pydevices[peripheralLabel].get_parent_label()  # type: ignore[return-value]

    def setParentLabel(
        self, deviceLabel: DeviceLabel | str, parentHubLabel: DeviceLabel | str
    ) -> None:
        if deviceLabel == KW.CoreDevice:
            return

        # Reject cross-language hub/peripheral relationships
        device_is_py = deviceLabel in self._pydevices
        parent_is_py = parentHubLabel in self._pydevices
        if parentHubLabel and device_is_py != parent_is_py:
            raise RuntimeError(  # pragma: no cover
                "Cannot set cross-language parent/child relationship between C++ and "
                "Python devices"
            )

        if device_is_py:
            self._pydevices[deviceLabel].set_parent_label(parentHubLabel)
        else:
            super().setParentLabel(deviceLabel, parentHubLabel)

    def getInstalledDevices(
        self, hubLabel: DeviceLabel | str
    ) -> tuple[DeviceName, ...]:
        if hubLabel not in self._pydevices:  # pragma: no cover
            return tuple(super().getInstalledDevices(hubLabel))

        with self._pydevices.get_device_of_type(hubLabel, HubDevice) as hub:
            peripherals = hub.get_installed_peripherals()
            return tuple(p[0] for p in peripherals if p[0])  # type: ignore[misc]

    def getLoadedPeripheralDevices(
        self, hubLabel: DeviceLabel | str
    ) -> tuple[DeviceLabel, ...]:
        cpp_peripherals = super().getLoadedPeripheralDevices(hubLabel)
        py_peripherals = self._pydevices.get_loaded_peripherals(hubLabel)
        return tuple(cpp_peripherals) + py_peripherals

    def getInstalledDeviceDescription(
        self, hubLabel: DeviceLabel | str, peripheralLabel: DeviceName | str
    ) -> str:
        if hubLabel not in self._pydevices:
            return super().getInstalledDeviceDescription(hubLabel, peripheralLabel)

        with self._pydevices.get_device_of_type(hubLabel, HubDevice) as hub:
            for p in hub.get_installed_peripherals():
                if p[0] == peripheralLabel:
                    return p[1] or "N/A"
            raise RuntimeError(  # pragma: no cover
                f"No peripheral with name {peripheralLabel!r} installed in hub "
                f"{hubLabel!r}"
            )

    # ---------------------------- Properties ---------------------------

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
            self._state_cache[(label, propName)] = value
        return value

    def getPropertyFromCache(
        self, deviceLabel: DeviceLabel | str, propName: PropertyName | str
    ) -> Any:
        if deviceLabel not in self._pydevices:  # pragma: no cover
            return super().getPropertyFromCache(deviceLabel, propName)
        return self._state_cache[(deviceLabel, propName)]

    def setProperty(
        self, label: str, propName: str, propValue: bool | float | int | str
    ) -> None:
        # FIXME:
        # this single case is probably just the tip of the iceberg when label is "Core"
        if label == KW.CoreDevice and propName == KW.CoreChannelGroup:
            self.setChannelGroup(str(propValue))
            return

        if label not in self._pydevices:  # pragma: no cover
            return super().setProperty(label, propName, propValue)
        with self._pydevices[label] as dev:
            dev.set_property_value(propName, propValue)
            self._state_cache[(label, propName)] = propValue

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
            return tuple(
                str(v) for v in (dev.get_property_info(propName).allowed_values or ())
            )

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
        # Get config data (merged from C++ and Python)
        cfg = self.getConfigData(group, configName, native=True)

        # Wait for each unique device in the config
        devs_to_await: set[str] = set()
        for i in range(cfg.size()):
            devs_to_await.add(cfg.getSetting(i).getDeviceLabel())

        for device in devs_to_await:
            try:
                self.waitForDevice(device)
            except Exception:
                # Like C++, trap exceptions and keep quiet
                pass

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
        seq = tuple(zip(xSequence, ySequence, strict=False))
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

    def getFocusDevice(self) -> DeviceLabel | Literal[""]:
        """Return the current Focus Device."""
        return self._pycore.current(KW.CoreFocus) or super().getFocusDevice()

    def setFocusDevice(self, focusLabel: str) -> None:
        """Set new current Focus Device."""
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

    @overload
    def getPosition(self) -> float: ...
    @overload
    def getPosition(self, stageLabel: str) -> float: ...
    def getPosition(self, stageLabel: str | None = None) -> float:
        label = stageLabel or self.getFocusDevice()
        if label not in self._pydevices:
            return super().getPosition(label)
        with self._pydevices.get_device_of_type(label, StageDevice) as device:
            return device.get_position_um()

    @overload
    def setPosition(self, position: float, /) -> None: ...
    @overload
    def setPosition(
        self, stageLabel: DeviceLabel | str, position: float, /
    ) -> None: ...
    def setPosition(self, *args: Any) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        label, args = _ensure_label(args, min_args=2, getter=self.getFocusDevice)
        if label not in self._pydevices:  # pragma: no cover
            return super().setPosition(label, *args)
        with self._pydevices.get_device_of_type(label, StageDevice) as dev:
            dev.set_position_um(*args)

    def setFocusDirection(self, stageLabel: DeviceLabel | str, sign: int) -> None:
        if stageLabel not in self._pydevices:  # pragma: no cover
            return super().setFocusDirection(stageLabel, sign)
        with self._pydevices.get_device_of_type(stageLabel, StageDevice) as device:
            device.set_focus_direction(sign)

    def getFocusDirection(self, stageLabel: DeviceLabel | str) -> FocusDirection:
        """Get the current focus direction of the Z stage."""
        if stageLabel not in self._pydevices:  # pragma: no cover
            return super().getFocusDirection(stageLabel)
        with self._pydevices.get_device_of_type(stageLabel, StageDevice) as device:
            return device.get_focus_direction()

    @overload
    def setOrigin(self) -> None: ...
    @overload
    def setOrigin(self, stageLabel: DeviceLabel | str) -> None: ...
    def setOrigin(self, stageLabel: DeviceLabel | str | None = None) -> None:
        """Zero the current focus/Z stage's coordinates at the current position."""
        label = stageLabel or self.getFocusDevice()
        if label not in self._pydevices:  # pragma: no cover
            return super().setOrigin(label)
        with self._pydevices.get_device_of_type(label, StageDevice) as device:
            device.set_origin()

    @overload
    def setRelativePosition(self, d: float, /) -> None: ...
    @overload
    def setRelativePosition(
        self, stageLabel: DeviceLabel | str, d: float, /
    ) -> None: ...
    def setRelativePosition(self, *args: Any) -> None:
        """Sets the relative position of the stage in microns."""
        label, args = _ensure_label(args, min_args=2, getter=self.getFocusDevice)
        if label not in self._pydevices:  # pragma: no cover
            return super().setRelativePosition(label, *args)
        with self._pydevices.get_device_of_type(label, StageDevice) as dev:
            dev.set_relative_position_um(*args)

    @overload
    def setAdapterOrigin(self, newZUm: float, /) -> None: ...
    @overload
    def setAdapterOrigin(
        self, stageLabel: DeviceLabel | str, newZUm: float, /
    ) -> None: ...
    def setAdapterOrigin(self, *args: Any) -> None:
        """Enable software translation of coordinates for the current focus/Z stage.

        The current position of the stage becomes Z = newZUm. Only some stages
        support this functionality; it is recommended that setOrigin() be used
        instead where available.
        """
        label, args = _ensure_label(args, min_args=2, getter=self.getFocusDevice)
        if label not in self._pydevices:  # pragma: no cover
            return super().setAdapterOrigin(label, *args)
        with self._pydevices.get_device_of_type(label, StageDevice) as dev:
            dev.set_adapter_origin_um(*args)

    def isStageSequenceable(self, stageLabel: DeviceLabel | str) -> bool:
        """Queries stage if it can be used in a sequence."""
        if stageLabel not in self._pydevices:  # pragma: no cover
            return super().isStageSequenceable(stageLabel)
        dev = self._pydevices.get_device_of_type(stageLabel, StageDevice)
        return dev.is_sequenceable()

    def isStageLinearSequenceable(self, stageLabel: DeviceLabel | str) -> bool:
        """Queries if the stage can be used in a linear sequence.

        A linear sequence is defined by a step size and number of slices.
        """
        if stageLabel not in self._pydevices:  # pragma: no cover
            return super().isStageLinearSequenceable(stageLabel)
        dev = self._pydevices.get_device_of_type(stageLabel, StageDevice)
        return dev.is_linear_sequenceable()

    def getStageSequenceMaxLength(self, stageLabel: DeviceLabel | str) -> int:
        """Gets the maximum length of a stage's position sequence."""
        if stageLabel not in self._pydevices:  # pragma: no cover
            return super().getStageSequenceMaxLength(stageLabel)
        dev = self._pydevices.get_device_of_type(stageLabel, StageDevice)
        return dev.get_sequence_max_length()

    def loadStageSequence(
        self,
        stageLabel: DeviceLabel | str,
        positionSequence: Sequence[float],
    ) -> None:
        """Transfer a sequence of stage positions to the stage.

        This should only be called for stages that are sequenceable.
        """
        if stageLabel not in self._pydevices:  # pragma: no cover
            return super().loadStageSequence(stageLabel, positionSequence)
        dev = self._pydevices.get_device_of_type(stageLabel, StageDevice)
        if len(positionSequence) > dev.get_sequence_max_length():
            raise ValueError(
                f"Sequence is too long. Max length is {dev.get_sequence_max_length()}"
            )
        dev.send_sequence(tuple(positionSequence))

    def startStageSequence(self, stageLabel: DeviceLabel | str) -> None:
        """Starts an ongoing sequence of triggered events in a stage.

        This should only be called for stages that are sequenceable.
        """
        if stageLabel not in self._pydevices:  # pragma: no cover
            return super().startStageSequence(stageLabel)
        with self._pydevices.get_device_of_type(stageLabel, StageDevice) as dev:
            dev.start_sequence()

    def stopStageSequence(self, stageLabel: DeviceLabel | str) -> None:
        """Stops an ongoing sequence of triggered events in a stage.

        This should only be called for stages that are sequenceable.
        """
        if stageLabel not in self._pydevices:  # pragma: no cover
            return super().stopStageSequence(stageLabel)
        with self._pydevices.get_device_of_type(stageLabel, StageDevice) as dev:
            dev.stop_sequence()

    def setStageLinearSequence(
        self, stageLabel: DeviceLabel | str, dZ_um: float, nSlices: int
    ) -> None:
        """Loads a linear sequence (defined by step size and nr. of steps)."""
        if nSlices < 0:
            raise ValueError("Linear sequence cannot have negative length")
        if stageLabel not in self._pydevices:  # pragma: no cover
            return super().setStageLinearSequence(stageLabel, dZ_um, nSlices)
        with self._pydevices.get_device_of_type(stageLabel, StageDevice) as dev:
            dev.set_linear_sequence(dZ_um, nSlices)

    def isContinuousFocusDrive(self, stageLabel: DeviceLabel | str) -> bool:
        """Check if a stage has continuous focusing capability.

        Returns True if positions can be set while continuous focus runs.
        """
        if stageLabel not in self._pydevices:  # pragma: no cover
            return super().isContinuousFocusDrive(stageLabel)
        dev = self._pydevices.get_device_of_type(stageLabel, StageDevice)
        return dev.is_continuous_focus_drive()

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
        x, y, *_ = cam.get_roi()
        camera_label = cam.get_label()

        n_components = shape[2] if len(shape) > 2 else 1
        base_meta: dict[str, Any] = {
            KW.Binning: cam.get_property_value(KW.Binning),
            KW.Metadata_CameraLabel: camera_label,
            KW.Metadata_Height: str(shape[0]),
            KW.Metadata_Width: str(shape[1]),
            KW.Metadata_ROI_X: str(x),
            KW.Metadata_ROI_Y: str(y),
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

    def _stop_acquisition_thread(self, timeout: float | None = 2) -> None:
        """Stop and join the python acquisition thread, if present."""
        if self._acquisition_thread is None:
            return
        self._stop_event.set()
        self._acquisition_thread.join(timeout=timeout)
        self._acquisition_thread = None

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
        self._stop_acquisition_thread()

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

        return 1

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
        if (cam := self._py_camera(label)) is not None:
            with cam:
                cam.set_roi(x, y, width, height)
            return
        return pymmcore.CMMCore.setROI(self, label, x, y, width, height)

    @overload
    def getROI(self) -> list[int]: ...
    @overload
    def getROI(self, label: DeviceLabel | str) -> list[int]: ...
    def getROI(self, label: DeviceLabel | str = "") -> list[int]:
        """Get the current region of interest (ROI) for the camera."""
        if (cam := self._py_camera(label)) is not None:
            with cam:
                return list(cam.get_roi())
        label = label or self.getCameraDevice()
        return super().getROI(label)

    def clearROI(self) -> None:
        """Clear the current region of interest (ROI) for the camera."""
        if (cam := self._py_camera()) is not None:
            with cam:
                cam.clear_roi()
            return
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

    @deprecated("No-op in MMCore >= 11.13; camera-dependent behavior in older")
    def prepareSequenceAcquisition(self, cameraLabel: DeviceLabel | str) -> None:
        """Prepare the camera for sequence acquisition."""
        if self._py_camera(cameraLabel) is None:  # pragma: no cover
            return super().prepareSequenceAcquisition(cameraLabel)

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

    # ########################################################################
    # -------------------- Configuration Group Methods -----------------------
    # ########################################################################
    #
    # HYBRID PATTERN: Config groups exist in both C++ and Python.
    # - Groups and presets are ALWAYS created in C++ (via super())
    # - _config_groups only stores settings for PYTHON devices
    # - Methods merge results from both systems where appropriate
    #
    # This ensures:
    # - C++ CoreCallback can find configs and emit proper events
    # - defineStateLabel in C++ can update configs referencing C++ devices
    # - loadSystemConfiguration works correctly
    # - Python device settings are properly tracked and applied

    # -------------------------------------------------------------------------
    # Group-level operations
    # -------------------------------------------------------------------------

    def defineConfigGroup(self, groupName: str) -> None:
        # Create group in C++ (handles validation and events)
        super().defineConfigGroup(groupName)
        # Also create empty group in Python for potential Python device settings
        self._py_config_groups[groupName] = {}

    def deleteConfigGroup(self, groupName: str) -> None:
        # Delete from C++ (handles validation and events)
        super().deleteConfigGroup(groupName)
        self._py_config_groups.pop(groupName, None)

    def renameConfigGroup(self, oldGroupName: str, newGroupName: str) -> None:
        # Rename in C++ (handles validation)
        super().renameConfigGroup(oldGroupName, newGroupName)
        if oldGroupName in self._py_config_groups:
            self._py_config_groups[newGroupName] = self._py_config_groups.pop(
                oldGroupName
            )

    # -------------------------------------------------------------------------
    # Preset-level operations
    # -------------------------------------------------------------------------

    @overload
    def defineConfig(self, groupName: str, configName: str) -> None: ...
    @overload
    def defineConfig(
        self,
        groupName: str,
        configName: str,
        deviceLabel: str,
        propName: str,
        value: Any,
    ) -> None: ...
    def defineConfig(
        self,
        groupName: str,
        configName: str,
        deviceLabel: str | None = None,
        propName: str | None = None,
        value: Any | None = None,
    ) -> None:
        # Route to appropriate storage based on device type
        if deviceLabel is None or propName is None or value is None:
            # No device specified: just create empty group/preset in C++
            super().defineConfig(groupName, configName)
            # Also ensure Python storage has the structure
            group = self._py_config_groups.setdefault(groupName, {})
            group.setdefault(cast("ConfigPresetName", configName), {})

        elif deviceLabel in self._pydevices:
            # Python device: store in our _config_groups
            # But first ensure the group/preset exists in C++ too
            if not super().isGroupDefined(groupName):
                super().defineConfigGroup(groupName)
                self._py_config_groups[groupName] = {}
            if not super().isConfigDefined(groupName, configName):
                super().defineConfig(groupName, configName)

            # Store Python device setting locally
            group = self._py_config_groups.setdefault(groupName, {})
            preset = group.setdefault(cast("ConfigPresetName", configName), {})
            preset[(deviceLabel, propName)] = value
            # Emit event (C++ won't emit for Python device settings)
            self.events.configDefined.emit(
                groupName, configName, deviceLabel, propName, str(value)
            )
        else:
            # C++ device: let C++ handle it entirely
            # C++ expects string values, so convert
            super().defineConfig(
                groupName, configName, deviceLabel, propName, str(value)
            )
            # Ensure our Python storage has the group/preset structure
            group = self._py_config_groups.setdefault(groupName, {})
            group.setdefault(cast("ConfigPresetName", configName), {})

    @overload
    def deleteConfig(self, groupName: str, configName: str) -> None: ...
    @overload
    def deleteConfig(
        self, groupName: str, configName: str, deviceLabel: str, propName: str
    ) -> None: ...
    def deleteConfig(
        self,
        groupName: str,
        configName: str,
        deviceLabel: str | None = None,
        propName: str | None = None,
    ) -> None:
        if deviceLabel is None or propName is None:
            # Deleting entire preset: delete from both C++ and Python storage
            py_group = self._py_config_groups.get(groupName, {})
            py_group.pop(configName, None)  # type: ignore[call-overload]
            super().deleteConfig(groupName, configName)

        # Deleting a specific property from a preset
        elif deviceLabel in self._pydevices:
            # Python device: remove from our storage
            py_group = self._py_config_groups.get(groupName, {})
            py_preset = py_group.get(configName, {})  # type: ignore[call-overload]
            key = (deviceLabel, propName)
            if key in py_preset:
                del py_preset[key]
                self.events.configDeleted.emit(groupName, configName)
            else:
                raise RuntimeError(
                    f"Property '{propName}' not found in preset '{configName}'"
                )
        else:
            # C++ device: let C++ handle it
            super().deleteConfig(groupName, configName, deviceLabel, propName)

    def renameConfig(
        self, groupName: str, oldConfigName: str, newConfigName: str
    ) -> None:
        # Rename in C++ (handles validation)
        super().renameConfig(groupName, oldConfigName, newConfigName)
        # Also rename in Python storage if present
        py_group = self._py_config_groups.get(groupName, {})
        if oldConfigName in py_group:
            py_group[newConfigName] = py_group.pop(oldConfigName)  # type: ignore

    @overload
    def getConfigData(
        self, configGroup: str, configName: str, *, native: Literal[True]
    ) -> pymmcore.Configuration: ...
    @overload
    def getConfigData(
        self, configGroup: str, configName: str, *, native: Literal[False] = False
    ) -> Configuration: ...
    def getConfigData(
        self, configGroup: str, configName: str, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        # Get C++ config data (includes all C++ device settings)
        cpp_cfg: pymmcore.Configuration = super().getConfigData(
            configGroup, configName, native=True
        )

        # Add Python device settings from our storage
        py_group = self._py_config_groups.get(configGroup, {})
        py_preset = py_group.get(configName, {})  # type: ignore[call-overload]
        for (dev, prop), value in py_preset.items():
            cpp_cfg.addSetting(pymmcore.PropertySetting(dev, prop, str(value)))

        if native:
            return cpp_cfg
        return Configuration.from_configuration(cpp_cfg)

    # -------------------------------------------------------------------------
    # Applying configurations
    # -------------------------------------------------------------------------

    def setConfig(self, groupName: str, configName: str) -> None:
        # Apply C++ device settings via super() - this handles validation,
        # error retry logic, and state cache updates for C++ devices
        super().setConfig(groupName, configName)

        # Now apply Python device settings from our storage
        py_group = self._py_config_groups.get(groupName, {})
        py_preset = py_group.get(configName, {})  # type: ignore[call-overload]

        if py_preset:
            failed: list[tuple[DevPropTuple, Any]] = []
            for (device, prop), value in py_preset.items():
                try:
                    self.setProperty(device, prop, value)
                except Exception:
                    failed.append(((device, prop), value))

            # Retry failed properties (handles dependency chains)
            if failed:
                errors: list[str] = []
                for (device, prop), value in failed:
                    try:
                        self.setProperty(device, prop, value)
                    except Exception as e:
                        errors.append(f"{device}.{prop}={value}: {e}")
                if errors:
                    raise RuntimeError("Failed to apply: " + "; ".join(errors))

    # -------------------------------------------------------------------------
    # Current config detection
    # -------------------------------------------------------------------------

    def getCurrentConfig(self, groupName: str) -> ConfigPresetName | Literal[""]:
        return self._getCurrentConfig(groupName, from_cache=False)

    def getCurrentConfigFromCache(
        self, groupName: str
    ) -> ConfigPresetName | Literal[""]:
        return self._getCurrentConfig(groupName, from_cache=True)

    def _getCurrentConfig(
        self, groupName: str, from_cache: bool
    ) -> ConfigPresetName | Literal[""]:
        """Find the first preset whose settings all match current device state.

        This checks both C++ device settings (via super()) and Python device settings.
        """
        # Get C++ result first
        if from_cache:
            cpp_result = super().getCurrentConfigFromCache(groupName)
        else:
            cpp_result = super().getCurrentConfig(groupName)

        # If no Python device settings exist for this group, C++ result is sufficient
        py_group = self._py_config_groups.get(groupName, {})
        has_py_settings = any(py_group.values())
        if not has_py_settings:
            return cpp_result

        # We have Python device settings - need to verify they match too
        # Get current state of all Python device properties in this group
        getter = self.getPropertyFromCache if from_cache else self.getProperty
        current_py_state: ConfigDict = {}
        seen_keys: set[DevPropTuple] = set()
        for preset in py_group.values():
            for key in preset:
                if key not in seen_keys:
                    seen_keys.add(key)
                    with suppress(Exception):
                        current_py_state[key] = getter(*key)

        # Check each preset to see if Python device settings match
        for preset_name in self.getAvailableConfigs(groupName):
            py_preset = py_group.get(preset_name, {})
            if all(
                _values_match(current_py_state.get(k), v) for k, v in py_preset.items()
            ):
                # Python settings match - but only return if C++ also matches
                # (or if there are no C++ settings for this preset)
                cpp_cfg = super().getConfigData(groupName, preset_name, native=True)
                if cpp_cfg.size() == 0:
                    # No C++ settings, Python match is sufficient
                    return preset_name
                # Check each C++ setting with numeric-aware comparison
                # (C++ getCurrentConfig uses strict string comparison which fails
                # for values like "50.0000" vs "50")
                all_cpp_match = True
                for i in range(cpp_cfg.size()):
                    setting = cpp_cfg.getSetting(i)
                    current_val = getter(
                        setting.getDeviceLabel(), setting.getPropertyName()
                    )
                    if not _values_match(current_val, setting.getPropertyValue()):
                        all_cpp_match = False
                        break
                if all_cpp_match:
                    return preset_name

        return ""

    # -------------------------------------------------------------------------
    # State queries
    # -------------------------------------------------------------------------

    def getConfigState(
        self, group: str, config: str, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        # Get C++ config state (current values for C++ device properties)
        cpp_state: pymmcore.Configuration = super().getConfigState(
            group, config, native=True
        )

        # Add current values for Python device properties
        py_group = self._py_config_groups.get(group, {})
        py_preset = py_group.get(config, {})  # type: ignore[call-overload]
        for dev, prop in py_preset:
            current_value = self.getProperty(dev, prop)
            cpp_state.addSetting(
                pymmcore.PropertySetting(dev, prop, str(current_value))
            )

        if native:
            return cpp_state
        return Configuration.from_configuration(cpp_state)

    @overload
    def getConfigGroupState(
        self, group: str, *, native: Literal[True]
    ) -> pymmcore.Configuration: ...
    @overload
    def getConfigGroupState(
        self, group: str, *, native: Literal[False] = False
    ) -> Configuration: ...
    def getConfigGroupState(
        self, group: str, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        return self._getConfigGroupState(group, from_cache=False, native=native)

    @overload
    def getConfigGroupStateFromCache(
        self, group: str, *, native: Literal[True]
    ) -> pymmcore.Configuration: ...
    @overload
    def getConfigGroupStateFromCache(
        self, group: str, *, native: Literal[False] = False
    ) -> Configuration: ...
    def getConfigGroupStateFromCache(
        self, group: str, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        return self._getConfigGroupState(group, from_cache=True, native=native)

    def _getConfigGroupState(
        self, group: str, from_cache: bool, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        """Get current values for all properties in a group."""
        # Get C++ group state
        if from_cache:
            cpp_state: pymmcore.Configuration = super().getConfigGroupStateFromCache(
                group, native=True
            )
        else:
            cpp_state = super().getConfigGroupState(group, native=True)

        # Add Python device property values
        py_group = self._py_config_groups.get(group, {})
        getter = self.getPropertyFromCache if from_cache else self.getProperty
        for preset in py_group.values():
            for device, prop in preset:
                value = str(getter(device, prop))
                cpp_state.addSetting(pymmcore.PropertySetting(device, prop, value))

        if native:
            return cpp_state
        return Configuration.from_configuration(cpp_state)

    # ########################################################################
    # ----------------------- System State Methods ---------------------------
    # ########################################################################

    # currently we still allow C++ to cache the system state for C++ devices,
    # but we could choose to just own it all ourselves in the future.

    def getSystemState(
        self, *, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        """Return the entire system state including Python device properties.

        This method iterates through all devices (C++ and Python) and returns
        all property values. Following the C++ implementation pattern.
        """
        return self._getSystemStateCache(cache=False, native=native)

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
        return self._getSystemStateCache(cache=True, native=native)

    def _getSystemStateCache(
        self, cache: bool, native: bool = False
    ) -> Configuration | pymmcore.Configuration:
        """Return the entire system state from cache, including Python devices.

        For Python devices, returns cached values from our state cache.
        Falls back to live values if not in cache.
        """
        # Get the C++ system state cache first
        if cache:
            cpp_cfg: pymmcore.Configuration = super().getSystemStateCache(native=True)
        else:
            cpp_cfg = super().getSystemState(native=True)

        # Add Python device properties from our cache
        for label in self._pydevices:
            with suppress(Exception):  # Skip devices that can't be accessed
                with self._pydevices[label] as dev:
                    for prop_name in dev.get_property_names():
                        with suppress(Exception):  # Skip properties that fail
                            key = (label, prop_name)
                            if cache and key in self._state_cache:
                                value = self._state_cache[key]
                            else:
                                value = dev.get_property_value(prop_name)
                            cpp_cfg.addSetting(
                                pymmcore.PropertySetting(
                                    label,
                                    prop_name,
                                    str(value),
                                    dev.is_property_read_only(prop_name),
                                )
                            )

        return cpp_cfg if native else Configuration.from_configuration(cpp_cfg)

    def updateSystemStateCache(self) -> None:
        """Update the system state cache for all devices including Python devices.

        This populates our Python-side cache with current values from all
        Python devices, then calls the C++ updateSystemStateCache.
        """
        # Update Python device properties in our cache
        for label in self._pydevices:
            with suppress(Exception):  # Skip devices that can't be accessed
                with self._pydevices[label] as dev:
                    for prop_name in dev.get_property_names():
                        with suppress(Exception):  # Skip properties that fail
                            value = dev.get_property_value(prop_name)
                            self._state_cache[(label, prop_name)] = value

        # Call C++ updateSystemStateCache
        super().updateSystemStateCache()


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


class ThreadSafeConfig(MutableMapping["DevPropTuple", Any]):
    """A thread-safe cache for property states.

    Keys are tuples of (device_label, property_name), and values are the last known
    value of that property.
    """

    def __init__(self) -> None:
        self._store: dict[DevPropTuple, Any] = {}
        self._lock = threading.Lock()

    def __getitem__(self, key: DevPropTuple) -> Any:
        with self._lock:
            try:
                return self._store[key]
            except KeyError:  # pragma: no cover
                dev, prop = key
                raise KeyError(
                    f"Property {prop!r} of device {dev!r} not found in cache"
                ) from None

    def __setitem__(self, key: DevPropTuple, value: Any) -> None:
        with self._lock:
            self._store[key] = value

    def __delitem__(self, key: DevPropTuple) -> None:
        with self._lock:
            del self._store[key]

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._store

    def __iter__(self) -> Iterator[DevPropTuple]:
        with self._lock:
            return iter(self._store.copy())  # Prevent modifications during iteration

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def __repr__(self) -> str:
        with self._lock:
            return f"{self.__class__.__name__}({self._store!r})"

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def clear_device(self, label: str) -> None:
        """Remove all entries for a given device label under a single lock."""
        with self._lock:
            keys = [k for k in self._store if k[0] == label]
            for key in keys:
                del self._store[key]


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


# --------- helpers -------------------------------------------------------


def _values_match(current: Any, expected: Any) -> bool:
    """Compare property values, handling numeric string comparisons.

    Unlike C++ MMCore which does strict string comparison, this performs
    numeric-aware comparison to handle cases like "50.0000" == 50.
    """
    if current == expected:
        return True
    # Try numeric comparison
    try:
        return float(current) == float(expected)
    except (ValueError, TypeError):
        return str(current) == str(expected)
