from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Container,
    Generic,
    TypeAlias,
    TypeVar,
)

from pymmcore_plus import CMMCorePlus, DeviceType, FocusDirection

from ._core_link import CoreObject
from ._property import CoreProperty, Property

if TYPE_CHECKING:
    from ._core_link import ErrCallback

    PropVal: TypeAlias = bool | float | int | str
    DeviceGetter: TypeAlias = Callable[[CMMCorePlus, str], Any]
    DeviceSetter: TypeAlias = Callable[[CMMCorePlus, str, Any], None]


PropertyType = TypeVar("PropertyType", bound="Property")
UNDEFINED = "UNDEFINED"


@dataclass
class Device(Generic[PropertyType]):
    """Model of a device."""

    name: str = UNDEFINED  # or label?
    library: str = ""
    adapter_name: str = ""
    description: str = ""
    device_type: DeviceType = DeviceType.Any  # perhaps UnknownType?
    properties: list[PropertyType] = field(default_factory=list)
    delay_ms: float = 0.0
    uses_delay: bool = False
    parent_label: str = ""

    initialized: bool = False

    # NOTE: I began by using device subclasses for these, but it becomes very difficult
    # when you need to "promote" a device to a different type. For example, if you are
    # loading a config file, and the only information you have is the device name, you
    # won't know what type of device it is until later. While you can theoretically
    # promote the class at that point, it gets very messy.  The following attributes
    # are used to store data specific to certain device types.

    # StateDevice only
    labels: dict[int, str] = field(default_factory=dict)

    # StageDevice only
    focus_direction: FocusDirection = FocusDirection.Unknown

    # HubDevice only
    children: tuple[str, ...] = field(default_factory=tuple)


class CoreDevice(Device, CoreObject):
    properties: list[CoreProperty] = field(default_factory=list)

    CORE_GETTERS: ClassVar[dict[str, DeviceGetter]] = {
        "library": CMMCorePlus.getDeviceLibrary,
        "adapter_name": CMMCorePlus.getDeviceName,
        "description": CMMCorePlus.getDeviceDescription,
        "device_type": CMMCorePlus.getDeviceType,
        "is_busy": CMMCorePlus.deviceBusy,
        "delay_ms": CMMCorePlus.getDeviceDelayMs,
        "uses_delay": CMMCorePlus.usesDeviceDelay,
        "parent_label": CMMCorePlus.getParentLabel,
        "property_names": CMMCorePlus.getDevicePropertyNames,
    }
    CORE_SETTERS: ClassVar[dict[str, DeviceSetter]] = {
        "delay_ms": CMMCorePlus.setDeviceDelayMs,
    }

    def _core_args(self) -> tuple[str]:
        return (self.name,)

    def follow_core(self, core: CMMCorePlus) -> None:
        core.events.propertyChanged.connect(self._on_core_change)

    def unfollow_core(self, core: CMMCorePlus) -> None:
        core.events.propertyChanged.disconnect(self._on_core_change)

    def _on_core_change(self, dev: str, prop: str, new_val: str) -> None:
        if dev == self.name and prop == self.name:
            self.value = new_val

    def update_from_core(
        self,
        core: CMMCorePlus,
        *,
        exclude: Container[str] = (),
        on_err: ErrCallback | None = None,
    ) -> None:
        """Update device properties from the core."""
        super().update_from_core(core)
        self.properties = [
            CoreProperty.create_from_core(core, device_name=self.name, name=p)
            for p in core.getDevicePropertyNames(self.name)
        ]

    def load(self, core: CMMCorePlus, *, reload: bool = False) -> None:
        """Load device properties from the core."""
        if reload and self.name in core.getLoadedDevices():
            core.unloadDevice(self.name)
        core.loadDevice(self.name, self.library, self.adapter_name)
        self.initialized = False

    def unload(self, core: CMMCorePlus) -> None:
        """Unload device from the core."""
        core.unloadDevice(self.name)

    def wait(self, core: CMMCorePlus) -> None:
        """Wait for device to finish."""
        core.waitForDevice(self.name)

    def detect(self, core: CMMCorePlus) -> None:
        """Detect device."""
        core.detectDevice(self.name)

    def initialize(
        self,
        core: CMMCorePlus,
        *,
        reload: bool = False,
        then_update: bool = True,
    ) -> None:
        """Initialize the device in core."""
        if reload:
            self.load(core, reload=reload)

        core.initializeDevice(self.name)
        self.initialized = True

        # if self.device_type == DeviceType.Serial:
        #     time.sleep(PORT_SLEEP)

        if then_update:
            self.update_from_core(core)
