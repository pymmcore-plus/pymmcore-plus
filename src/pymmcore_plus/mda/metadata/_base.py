from __future__ import annotations

import warnings
from abc import abstractmethod
from inspect import signature
from typing import TYPE_CHECKING, Any, Callable, Literal, cast

if TYPE_CHECKING:
    from typing import Protocol

    from pymmcore_plus.core import CMMCorePlus

    class MetaDataGetter(Protocol):
        """Callable that fetches metadata."""

        def __call__(self, core: CMMCorePlus, extra: dict[str, Any]) -> Any:
            """Must core and `extra` dict.

            May search for keys in `extra` to modify behavior.
            """


__all__ = ["MetadataProvider", "get_metadata_func", "ensure_valid_metadata_func"]


# we don't actually inherit from (ABC) here so as to avoid metaclass conflicts
# this means the @abstractmethod decorator is not actually enforced,
# however, it will raise an exception if the method is not implemented when gathering
# metadata providers in
class MetadataProvider:
    """Base class for metadata providers.

    Any subclasses that implement these methods will be automatically registered
    as metadata providers, provided that they have been imported before the
    `get_metadata_func` function is called.
    """

    @classmethod
    @abstractmethod
    def from_core(cls, core: CMMCorePlus, extra: dict[str, Any]) -> Any:
        raise NotImplementedError(f"{cls.__name__} must implement `from_core` method.")

    @classmethod
    @abstractmethod
    def provider_key(cls) -> str:
        raise NotImplementedError(
            f"{cls.__name__} must implement `provider_key` method."
        )

    @classmethod
    @abstractmethod
    def provider_version(cls) -> str:
        raise NotImplementedError(
            f"{cls.__name__} must implement `provider_version` method."
        )

    @classmethod
    @abstractmethod
    def metadata_type(cls) -> Literal["summary", "frame"]:
        raise NotImplementedError(
            f"{cls.__name__} must implement `metadata_type` method."
        )


_METADATA_GETTERS: dict[str, dict[str, MetaDataGetter]] = {}


def _build_metadata_getters() -> None:
    # import all of our known providers here, before we start building the dict
    from . import _legacy, _structs  # noqa: F401

    for subcls in MetadataProvider.__subclasses__():
        try:
            key = subcls.provider_key()
            version = subcls.provider_version()
        except Exception as e:
            warnings.warn(
                f"Failed to register pymmcore-plus metadata provider {subcls}: {e}",
                RuntimeWarning,
                stacklevel=2,
            )
        sub_dict = _METADATA_GETTERS.setdefault(key, {})
        if version in sub_dict:
            raise ValueError(
                f"Duplicate metadata provider: {key}/{version} "
                f"({subcls} and {sub_dict[version]})"
            )
        sub_dict[version] = subcls.from_core


def get_metadata_func(key: str, version: str = "1.0") -> MetaDataGetter:
    """Return a function that can fetch metadata in the specified format and version."""
    if "." not in version and len(version) == 1:
        version += ".0"

    if not _METADATA_GETTERS:
        _build_metadata_getters()

    try:
        return _METADATA_GETTERS[key][version]
    except KeyError:
        options = ", ".join(
            f"{fmt}/{ver}"
            for fmt, versions in _METADATA_GETTERS.items()
            for ver in versions
        )
        raise ValueError(
            f"Unsupported metadata format/version: {key}/{version}. Options: {options}"
        ) from None


def ensure_valid_metadata_func(obj: Callable) -> MetaDataGetter:
    """Ensure that `obj` is a valid metadata function and return it.

    A valid metadata function is a callable with the following signature:

    ```python
    def metadata_func(core: CMMCorePlus, extra: dict[str, Any]) -> Any: ...
    ```
    """
    if not callable(obj):
        raise TypeError(f"Expected callable, got {type(obj)}")
    sig = signature(obj)
    if len(sig.parameters) != 2:
        raise TypeError(
            "Metadata function should accept 2 parameters "
            f"(core: CMMCorePlus, extra: dict), got {len(sig.parameters)}"
        )
    return cast("MetaDataGetter", obj)
