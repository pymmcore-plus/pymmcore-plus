from __future__ import annotations

import logging
import threading
from abc import ABC
from collections import ChainMap
from enum import EnumMeta
from functools import wraps
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, final

from pymmcore_plus.core import DeviceType
from pymmcore_plus.core._constants import PropertyType
from pymmcore_plus.experimental.unicore.devices._properties import (
    PropertyController,
    PropertyInfo,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable, KeysView, Sequence

    from pymmcore_nano import DeviceCallbacks
    from pymmcore_nano.protocols import CreatePropertyFn
    from typing_extensions import Any, Self

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
        return self._lock.acquire(blocking, timeout)  # pragma: no cover

    def unlock(self) -> None:
        self._lock.release()  # pragma: no cover

    def locked(self) -> bool:
        return self._lock.locked()  # pragma: no cover


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
        self._parent_label_: str = ""  # label of the parent hub device
        # PropertyHandle refs for dynamic property updates via C++ bridge
        self._property_handles_: dict[str, Any] = {}
        # DeviceCallbacks for notifying CMMCore (set during initialize)
        self._notify_: DeviceCallbacks | None = None

    def __init_subclass__(cls) -> None:
        """Initialize the property controllers and wrap initialize for bridge."""
        cls._cls_prop_controllers = {}
        for base in cls.__mro__:
            for p in base.__dict__.values():
                if isinstance(p, PropertyController):
                    cls._cls_prop_controllers[p.property.name] = p

        # Wrap user-defined initialize() so C++ bridge can call it with
        # (create_property, notify) args while user code defines initialize(self).
        if "initialize" in cls.__dict__:
            user_init = cls.__dict__["initialize"]
            # Only wrap if the user's initialize doesn't already accept bridge args
            if callable(user_init) and getattr(user_init, "__code__", None):
                nargs = user_init.__code__.co_argcount  # includes self
                if nargs == 1:  # just (self,)
                    cls.initialize = Device._wrap_initialize(user_init)

        return super().__init_subclass__()

    @staticmethod
    def _wrap_initialize(user_init: Callable) -> Callable:
        """Wrap a device author's initialize(self) to accept bridge args.

        The C++ bridge calls initialize(create_property, notify). Device authors
        write initialize(self) with no extra args. This wrapper bridges the gap.
        """

        @wraps(user_init)
        def bridge_initialize(
            dev: Device, create_property: Any = None, notify: Any = None
        ) -> None:
            if notify is not None:
                dev._notify_ = notify
            try:
                user_init(dev)
                dev._initialized_ = True
            except Exception as e:
                dev._initialized_ = e
                logger.exception(f"Failed to initialize device {dev.get_label()!r}")
                return  # Don't register properties if init failed
            if create_property is not None:
                dev._register_bridge_properties(create_property)
                dev._post_bridge_initialize()

        return bridge_initialize

    def _register_bridge_properties(self, create_property: CreatePropertyFn) -> None:
        for ctrl in self._prop_controllers_.values():
            _register_one_property(self, ctrl, create_property)

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
        sequence_loader: Callable[[TDev, Sequence[TProp]], None] | None = None,
        sequence_starter: Callable[[TDev], None] | None = None,
        sequence_stopper: Callable[[TDev], None] | None = None,
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

        if isinstance(property_type, EnumMeta) and allowed_values is None:
            allowed_values = tuple(property_type)

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
        controller = PropertyController(
            property=prop_info,
            fget=getter,
            fset=setter,
            fseq_load=sequence_loader,
            fseq_start=sequence_starter,
            fseq_stop=sequence_stopper,
        )
        self._prop_controllers_[name] = controller

    def initialize(self, create_property: Any = None, notify: Any = None) -> None:
        """Initialize the device.

        The C++ bridge calls this with (create_property, notify). Device authors
        override this with no extra args — __init_subclass__ wraps it automatically.
        """
        if notify is not None:
            self._notify_ = notify
        self._initialized_ = True
        if create_property is not None:
            self._register_bridge_properties(create_property)
            self._post_bridge_initialize()

    def _post_bridge_initialize(self) -> None:
        """Hook called after bridge properties are registered.

        Subclasses (e.g. StateDevice) can override to perform additional
        C++ bridge setup that depends on properties being registered first.
        """

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

    def _get_prop_or_raise(self, prop_name: str) -> PropertyController:
        """Get a property controller by name or raise an error."""
        if prop_name not in self._prop_controllers_:
            raise KeyError(
                f"Device {self.get_label()!r} has no property {prop_name!r}."
            )
        return self._prop_controllers_[prop_name]

    def has_property(self, prop_name: str) -> bool:
        """Return `True` if the device has a property with the given name."""
        return prop_name in self._prop_controllers_

    def get_property_names(self) -> KeysView[str]:
        """Return the names of the properties."""
        return self._prop_controllers_.keys()

    def get_property_info(self, prop_name: str) -> PropertyInfo:
        """Return the property controller for a property."""
        return self._get_prop_or_raise(prop_name).property

    def get_property_value(self, prop_name: str) -> Any:
        """Return the value of a property."""
        # TODO: catch errors
        ctrl = self._get_prop_or_raise(prop_name)
        if ctrl.fget is None:
            return ctrl.property.last_value
        return ctrl.__get__(self, self.__class__)

    def set_property_value(self, prop_name: str, value: Any) -> None:
        """Set the value of a property."""
        # TODO: catch errors
        ctrl = self._get_prop_or_raise(prop_name)
        if ctrl.is_read_only:
            raise ValueError(f"Property {prop_name!r} is read-only.")
        if ctrl.fset is not None:
            ctrl.__set__(self, value)
        else:
            ctrl.property.last_value = ctrl.validate(value)

    def set_property_allowed_values(
        self, prop_name: str, allowed_values: Sequence[Any]
    ) -> None:
        """Set the allowed values of a property."""
        self._get_prop_or_raise(prop_name).property.allowed_values = allowed_values
        if prop_name in self._property_handles_:
            self._property_handles_[prop_name].set_allowed_values(
                [str(v) for v in allowed_values]
            )

    def set_property_limits(
        self, prop_name: str, limits: tuple[float, float] | None
    ) -> None:
        """Set the limits of a property."""
        self._get_prop_or_raise(prop_name).property.limits = limits
        if limits is not None and prop_name in self._property_handles_:
            self._property_handles_[prop_name].set_limits(
                float(limits[0]), float(limits[1])
            )

    def set_property_sequence_max_length(self, prop_name: str, max_length: int) -> None:
        """Set the sequence max length of a property."""
        self._get_prop_or_raise(prop_name).property.sequence_max_length = max_length
        if prop_name in self._property_handles_:
            self._property_handles_[prop_name].set_sequence_max_length(max_length)

    def load_property_sequence(self, prop_name: str, sequence: Sequence[Any]) -> None:
        """Load a sequence into a property."""
        self._get_prop_or_raise(prop_name).load_sequence(self, sequence)

    def start_property_sequence(self, prop_name: str) -> None:
        """Start a sequence of a property."""
        self._get_prop_or_raise(prop_name).start_sequence(self)

    def stop_property_sequence(self, prop_name: str) -> None:
        """Stop a sequence of a property."""
        self._get_prop_or_raise(prop_name).stop_sequence(self)

    def is_property_sequenceable(self, prop_name: str) -> bool:
        """Return `True` if the property is sequenceable."""
        return self._get_prop_or_raise(prop_name).is_sequenceable

    def is_property_read_only(self, prop_name: str) -> bool:
        """Return `True` if the property is read-only."""
        return self._get_prop_or_raise(prop_name).is_read_only

    # PARENT HUB RELATIONSHIP

    @final  # may not be overridden
    def get_parent_label(self) -> str:
        """Return the label of the parent hub device, or empty string if none."""
        return self._parent_label_

    @final  # may not be overridden
    def set_parent_label(self, parent_label: str) -> None:
        """Set the label of the parent hub device."""
        self._parent_label_ = parent_label


SeqT = TypeVar("SeqT")


class SequenceableDevice(Device, Generic[SeqT]):
    """ABC For devices that can handle sequences of values.

    This is used for *most* device classes (XYStage, State, etc...). We
    convert the core `is<>Sequenceable` methods into a call to the
    `is_property_sequenceable` method on the "current" device of that type.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @final
    def is_sequenceable(self) -> bool:
        """Return `True` if the device is sequenceable. Default is `False`."""
        if self.get_sequence_max_length() == 0:
            return False

        # A device is sequenceable if it returns a max sequence length > 0 AND
        # has reimplemented the send_sequence and start_sequence methods.
        # we climb the method resolution chain and make sure that at least one base
        # class has reimplemented these methods.
        mro = self.__class__.mro()
        send_sequence_definer = next(b for b in mro if "send_sequence" in b.__dict__)
        start_sequence_definer = next(b for b in mro if "start_sequence" in b.__dict__)
        return (
            send_sequence_definer is not SequenceableDevice
            and start_sequence_definer is not SequenceableDevice
        )

    def get_sequence_max_length(self) -> int:
        """Return the sequence."""
        return 0

    def send_sequence(self, sequence: tuple[SeqT, ...]) -> None:
        """Signal that we are done appending sequence values.

        So that the adapter can send the whole sequence to the device
        """
        raise NotImplementedError("This device has not been made sequenceable.")

    def start_sequence(self) -> None:
        """Start the sequence."""
        raise NotImplementedError("This device has not been made sequenceable.")

    def stop_sequence(self) -> None:
        """Stop the sequence."""


# MM property type enum values (matches MM::PropertyType in C++)
_PROP_TYPE_MAP: dict[PropertyType, int] = {
    PropertyType.Undef: 1,  # MM::String
    PropertyType.String: 1,  # MM::String
    PropertyType.Float: 2,  # MM::Float
    PropertyType.Integer: 3,  # MM::Integer
    PropertyType.Boolean: 1,  # store as string
    PropertyType.Enum: 1,  # store as string
}


def _register_one_property(
    device: Device, ctrl: PropertyController, create_property: CreatePropertyFn
) -> None:
    info = ctrl.property
    prop_type = info.type
    default_str = str(info.default_value) if info.default_value is not None else ""

    if (limits := info.limits) is not None:
        limits = (float(limits[0]), float(limits[1]))

    if (allowed := info.allowed_values) is not None:
        allowed = [str(v) for v in allowed]

    # The C++ bridge expects all property values as strings, so we use the prop_type's
    # parse_value method to convert from string to the appropriate Python type in the
    # setter and sequence loader.
    _parse = prop_type.parse_value
    setter = (lambda s: ctrl.fset(device, _parse(s))) if ctrl.fset else None
    seq_loader = (
        (lambda seq: ctrl.load_sequence(device, [_parse(s) for s in seq]))
        if ctrl.fseq_load
        else None
    )

    device._property_handles_[info.name] = create_property(
        info.name,
        default_str,
        _PROP_TYPE_MAP.get(prop_type, 1),
        ctrl.is_read_only,
        getter=ctrl.fget.__get__(device) if ctrl.fget else None,
        setter=setter,
        pre_init=info.is_pre_init,
        limits=limits,
        allowed_values=allowed,
        sequence_max_length=info.sequence_max_length if ctrl.is_sequenceable else 0,
        sequence_loader=seq_loader,
        sequence_starter=ctrl.fseq_start.__get__(device) if ctrl.fseq_start else None,
        sequence_stopper=ctrl.fseq_stop.__get__(device) if ctrl.fseq_stop else None,
    )
