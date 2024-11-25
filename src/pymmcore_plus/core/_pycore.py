from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Literal, Self, cast, overload

from pymmcore_plus.core._constants import DeviceType, Keyword

from ._mmcore_plus import CMMCorePlus

if TYPE_CHECKING:
    from collections.abc import Iterator, KeysView, Sequence

    from pymmcore import DeviceLabel


class _Lockable:
    """Mixin to make an object lockable."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._lock = threading.Lock()

    def __enter__(self) -> Self:
        self._lock.acquire()
        return self

    def __exit__(self, *args: Any) -> None:
        self._lock.release()

    def lock(self, blocking: bool = True, timeout: float = -1) -> bool:
        return self._lock.acquire(blocking, timeout)

    def unlock(self) -> None:
        self._lock.release()

    def locked(self) -> bool:
        return self._lock.locked()


class Device(_Lockable, ABC):
    """ABC for all Devices."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    @abstractmethod
    def type(self) -> DeviceType: ...


class XYStageDevice(Device, ABC):
    """ABC for XYStage devices."""

    def type(self) -> Literal[DeviceType.XYStage]:
        return DeviceType.XYStage

    @abstractmethod
    def set_position(self, x: float, y: float) -> None: ...
    @abstractmethod
    def get_position(self) -> tuple[float, float]: ...


class PyDeviceManager:
    """Manages loaded Python devices."""

    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}

    def load_device(self, label: str, device: Device) -> None:
        if label in self._devices:
            raise ValueError(f"The specified device label {label!r} is already in use")
        # TODO other stuff
        self._devices[label] = device

    def unload_device(self, device: str | Device) -> None:
        if isinstance(device, Device):
            label = next(k for k, v in self._devices.items() if v is device)
        else:
            label = device
        self._devices.pop(label, None)  # TODO ... check existence

    def unload_all_devices(self) -> None:
        self._devices.clear()  # TODO ...

    def keys(self) -> KeysView[str]:
        return self._devices.keys()

    def __len__(self) -> int:
        return len(self._devices)

    def __iter__(self) -> Iterator[str]:
        return iter(self._devices)

    def __contains__(self, label: str) -> bool:
        return label in self._devices

    def __getitem__(self, label: str) -> Device:
        if label not in self._devices:
            raise KeyError(f"No device with label '{label!r}'")
        return self._devices[label]

    def get_device(self, label: str) -> Device:
        return self[label]

    def get(self, label: str) -> Device | None:
        return self._devices.get(label, None)

    @overload
    def require_device_type(
        self, label: str, type: Literal[DeviceType.XYStage]
    ) -> XYStageDevice: ...
    @overload
    def require_device_type(self, label: str, type: DeviceType) -> Device: ...

    def require_device_type(self, label: str, type: DeviceType) -> Device:
        device = self[label]
        if device.type() != type:
            raise ValueError(
                f"Device {label!r} is of the wrong type for the requested operation"
            )
        return device


class UniMMCore(CMMCorePlus):
    """Unified Core object that first checks for python, then C++ devices."""

    def __init__(self, mm_path: str | None = None, adapter_paths: Sequence[str] = ()):
        super().__init__(mm_path, adapter_paths)
        self._pydevices = PyDeviceManager()

        # TODO: make virtual PyCoreDevice class
        self._pycurrent: dict[Keyword, DeviceLabel | None] = {
            Keyword.CoreCamera: None,
            Keyword.CoreShutter: None,
            Keyword.CoreFocus: None,
            Keyword.CoreXYStage: None,
            Keyword.CoreAutoFocus: None,
            Keyword.CoreSLM: None,
            Keyword.CoreGalvo: None,
        }

    def load_py_device(self, label: str, device: Device) -> None:
        # prevent conflicts with CMMCore device names
        if label in self.getLoadedDevices():
            raise ValueError(f"The specified device label {label!r} is already in use")
        self._pydevices.load_device(label, device)

    # ---------------------------- XYStageDevice ----------------------------

    def setXYStageDevice(self, xyStageLabel: DeviceLabel | str) -> None:
        # if this is a recognized PyCore device, set it as the current device
        if xyStageLabel in self._pydevices:
            self._pycurrent[Keyword.CoreXYStage] = cast("DeviceLabel", xyStageLabel)
            # and stop tracking the device in the CMMCore device
            xyStageLabel = ""  # reset CMMCore device
        super().setXYStageDevice(xyStageLabel)

    def getXYStageDevice(self) -> DeviceLabel | Literal[""]:
        return self._pycurrent[Keyword.CoreXYStage] or super().getXYStageDevice()

    @overload
    def setXYPosition(self, x: float, y: float, /) -> None: ...
    @overload
    def setXYPosition(self, xyStageLabel: str, x: float, y: float, /) -> None: ...
    def setXYPosition(self, *args: Any) -> None:
        if len(args) == 3:
            label, x, y = args
        elif len(args) == 2:
            x, y = args
            label = self.getXYStageDevice()

        if label not in self._pydevices:
            return super().setXYPosition(label, x, y)

        with self._pydevices.require_device_type(label, DeviceType.XYStage) as dev:
            dev.set_position(x, y)

    def getXYPosition(
        self, xyStageLabel: DeviceLabel | str = ""
    ) -> tuple[float, float]:
        """Obtains the current position of the XY stage in microns."""
        label = xyStageLabel or self.getXYStageDevice()
        if label not in self._pydevices:
            return tuple(super().getXYPosition(label))  # type: ignore

        with self._pydevices.require_device_type(label, DeviceType.XYStage) as dev:
            return dev.get_position()

    # ---------------------------- ... ----------------------------
