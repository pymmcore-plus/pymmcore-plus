from __future__ import annotations

import threading
from abc import ABC
from collections import ChainMap
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Generic, TypeVar, final

from pymmcore_plus.core import DeviceType
from pymmcore_plus.core._constants import PropertyType
from pymmcore_plus.experimental.unicore.devices._properties import (
    PropertyController,
    PropertyInfo,
)

if TYPE_CHECKING:
    from collections.abc import KeysView, Sequence

    from typing_extensions import Any, Self

    from pymmcore_plus.core._proxy import CMMCoreProxy

    from ._properties import PropArg, TDev, TProp


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

    _TYPE: ClassVar[DeviceType] = DeviceType.UnknownType
    _cls_prop_controllers: ClassVar[dict[str, PropertyController]]

    def __init__(self) -> None:
        super().__init__()

        # NOTE: The following attributes are here for the core to manipulate.
        # Device Adapter subclasses should not touch these attributes.
        self._label_: str = ""
        self._initialized_: bool | BaseException = False
        self._prop_controllers_ = ChainMap[str, PropertyController](
            {}, self._cls_prop_controllers
        )
        self._core_proxy_: CMMCoreProxy | None = None

    @property
    def core(self) -> CMMCoreProxy:
        """The device may use this to access a restricted subset of the Core API."""
        if self._core_proxy_ is None:
            raise AttributeError("CoreProxy not set. Has this device been loaded?")
        return self._core_proxy_

    def __init_subclass__(cls) -> None:
        """Initialize the property controllers."""
        cls._cls_prop_controllers = {
            p.property.name: p
            for p in cls.__dict__.values()
            if isinstance(p, PropertyController)
        }
        return super().__init_subclass__()

    def register_property(
        self,
        name: str,
        *,
        default_value: TProp | None = None,
        getter: Callable[[TDev], TProp] | None = None,
        setter: Callable[[TDev, TProp], None] | None = None,
        limits: tuple[int | float, int | float] | None = None,
        sequence_max_length: int = 0,
        allowed_values: Sequence[TProp] | None = None,
        is_read_only: bool = False,
        is_pre_init: bool = False,
        property_type: PropArg = None,
    ) -> None:
        """Manually register a property.

        This is an alternative to using the `@pymm_property` decorator.  It can be used
        to register properties that are not defined in the class body.  This is useful
        for pure "user-side" properties that are not used by the adapter, but which the
        adapter may want to access (such as a preference or a configuration setting
        that doesn't affect the device's behavior, but which the adapter may want to
        read).

        Properties defined this way are not accessible as class attributes.
        """
        if property_type is None and default_value is not None:
            property_type = type(default_value)

        prop_info = PropertyInfo(
            name=name,
            default_value=default_value,
            last_value=default_value,
            limits=limits,
            sequence_max_length=sequence_max_length,
            description="",
            allowed_values=allowed_values,
            is_read_only=is_read_only,
            is_pre_init=is_pre_init,
            type=PropertyType.create(property_type),
        )
        controller = PropertyController(property=prop_info, fget=getter, fset=setter)
        self._prop_controllers_[name] = controller

    def initialize(self) -> None:
        """Initialize the device."""

    def shutdown(self) -> None:
        """Shutdown the device."""

    @final  # may not be overridden
    def get_label(self) -> str:
        return self._label_

    @final  # may not be overridden
    @classmethod
    def type(cls) -> DeviceType:
        """Return the type of the device."""
        return cls._TYPE

    @classmethod
    def name(cls) -> str:
        """Return the name of the device."""
        return f"{cls.__name__}"

    def description(self) -> str:
        """Return a description of the device."""
        return self.__doc__ or ""

    def busy(self) -> bool:
        """Return `True` if the device is busy."""
        return False

    # PROPERTIES

    def get_property_names(self) -> KeysView[str]:
        """Return the names of the properties."""
        return self._prop_controllers_.keys()

    def property(self, prop_name: str) -> PropertyInfo:
        """Return the property controller for a property."""
        return self._prop_controllers_[prop_name].property

    def get_property_value(self, prop_name: str) -> Any:
        """Return the value of a property."""
        # TODO: catch errors
        ctrl = self._prop_controllers_[prop_name]
        if ctrl.fget is None:
            return ctrl.property.last_value
        return self._prop_controllers_[prop_name].__get__(self, self.__class__)

    def set_property_value(self, prop_name: str, value: Any) -> None:
        """Set the value of a property."""
        # TODO: catch errors
        ctrl = self._prop_controllers_[prop_name]
        if ctrl.is_read_only:
            raise ValueError(f"Property {prop_name!r} is read-only.")
        if ctrl.fset is not None:
            ctrl.__set__(self, value)
        else:
            ctrl.property.last_value = ctrl.validate(value)

    def load_property_sequence(self, prop_name: str, sequence: Sequence[Any]) -> None:
        """Load a sequence into a property."""
        self._prop_controllers_[prop_name].load_sequence(self, sequence)

    def start_property_sequence(self, prop_name: str) -> None:
        """Start a sequence of a property."""
        self._prop_controllers_[prop_name].start_sequence(self)

    def stop_property_sequence(self, prop_name: str) -> None:
        """Stop a sequence of a property."""
        self._prop_controllers_[prop_name].stop_sequence(self)

    def set_property_allowed_values(
        self, prop_name: str, allowed_values: Sequence[Any]
    ) -> None:
        """Set the allowed values of a property."""
        self._prop_controllers_[prop_name].property.allowed_values = allowed_values

    def set_property_limits(
        self, prop_name: str, limits: tuple[float, float] | None
    ) -> None:
        """Set the limits of a property."""
        self._prop_controllers_[prop_name].property.limits = limits

    def set_property_sequence_max_length(self, prop_name: str, max_length: int) -> None:
        """Set the sequence max length of a property."""
        self._prop_controllers_[prop_name].property.sequence_max_length = max_length

    def is_property_sequenceable(self, prop_name: str) -> bool:
        """Return `True` if the property is sequenceable."""
        return self._prop_controllers_[prop_name].is_sequenceable

    def is_property_read_only(self, prop_name: str) -> bool:
        """Return `True` if the property is read-only."""
        return self._prop_controllers_[prop_name].is_read_only


SeqT = TypeVar("SeqT")


class SequenceableDevice(Device, Generic[SeqT]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # Note, for this base implementation, the type of the value is SeqT, which is a
        # variable that depends on the device type.  For example, for a stage device,
        # SeqT would be a float, but for an XYStage device, SeqT would be a tuple[float,
        # float].  It is up to the final subclass to handle this correctly when they
        # send the sequence to the device... or to reimplement more methods on this
        # class if they need different behavior.
        self._sequence: list[SeqT] = []

    # TODO: do we need both of these?  can't we just use max_length?
    def is_sequenceable(self) -> bool:
        """Return `True` if the device is sequenceable. Default is `False`."""
        return self.get_sequence_max_length() > 0

    def get_sequence_max_length(self) -> int:
        """Return the sequence."""
        return 0

    def add_to_sequence(self, value: SeqT) -> None:
        """Add a value to the sequence."""
        self._sequence.append(value)

    def clear_sequence(self) -> None:
        """Remove all values from the sequence."""
        self._sequence.clear()

    def start_sequence(self) -> None:
        """Start the sequence."""

    def stop_sequence(self) -> None:
        """Stop the sequence."""

    def send_sequence(self) -> None:
        """Signal that we are done appending sequence values.

        So that the adapter can send the whole sequence to the device
        """
        if self._sequence:
            raise NotImplementedError(
                "Sequence has been accumulated but send_sequence is not implemented."
            )
