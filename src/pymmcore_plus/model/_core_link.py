from __future__ import annotations

import abc
from dataclasses import fields
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Container,
    Iterable,
    Protocol,
    TypeAlias,
    TypeVar,
)

if TYPE_CHECKING:
    from dataclasses import Field

    from pymmcore_plus import CMMCorePlus

    ErrCallback: TypeAlias = Callable[["CoreObject", str, Exception], Any]
    T = TypeVar("T", bound="CoreObject")


class CoreObject(Protocol):
    @abc.abstractmethod
    def _core_args(self) -> tuple[str, ...]:
        ...

    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    CORE_GETTERS: ClassVar[dict[str, Callable]]

    @classmethod
    def create_from_core(
        cls: type[T], core: CMMCorePlus, *args: Any, **kwargs: Any
    ) -> T:
        obj = cls(*args, **kwargs)
        obj.update_from_core(core)
        return obj

    def update_from_core(
        self,
        core: CMMCorePlus,
        *,
        exclude: Container[str] = (),
        on_err: ErrCallback | None = None,
    ) -> None:
        field_names = {
            f.name
            for f in fields(self)
            if f.name in self.CORE_GETTERS and f.name not in exclude
        }

        for field_name, val in self.core_values(core, field_names, on_err):
            if field_name in field_names:
                setattr(self, field_name, val)

    def core_values(
        self,
        core: CMMCorePlus,
        field_names: Iterable[str] | None = None,
        on_err: ErrCallback | None = None,
    ) -> Iterable[tuple[str, Any]]:
        if field_names is None:
            field_names = {f.name for f in fields(self)}

        args = self._core_args()
        for field_name, getter in self.CORE_GETTERS.items():
            try:
                yield field_name, getter(core, *args)
            except RuntimeError as e:
                if callable(on_err):
                    on_err(self, field_name, e)

    # consider removing and making abstract...
    # there generally aren't enough setters to justify this
    @abc.abstractmethod
    def apply_to_core(
        self,
        core: CMMCorePlus,
        *,
        exclude: Container[str] = (),
        on_err: ErrCallback | None = None,
        then_update: bool = True,
    ) -> None:
        ...
        # field_names = {
        #     f.name
        #     for f in fields(self)
        #     if f.name in self.CORE_SETTERS and f.name not in exclude
        # }

        # core_args = self._core_args()

        # for field_name in field_names:
        #     try:
        #         val = getattr(self, field_name)
        #         self.CORE_SETTERS[field_name](core, *core_args, val)
        #     except RuntimeError as e:
        #         if callable(on_err):
        #             on_err(self, field_name, e)

        # # to prevent desynchronization in case of errors in setting
        # if then_update:
        #     self.update_from_core(core)

    def __rich_repr__(
        self, *, exclude: Container[str] = (), defaults: bool = False
    ) -> Iterable[tuple[str, Any]]:
        """Make AvailableDevices look a little less verbose."""
        for f in fields(self):
            if f.name in exclude or f.repr is False:
                continue
            val = getattr(self, f.name)
            default = f.default_factory() if callable(f.default_factory) else f.default
            if defaults or val != default:
                yield f.name, val
