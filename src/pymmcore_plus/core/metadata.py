"""Metadata schema.

These operations and types define various metadata payloads.

All metadata payloads are dictionaries with string keys and values of any type.
- They *all* include a "format" key with a string value that identifies the
  type/format of the metadata (such as summary or frame metadata).
- They *all* include a "version" key with a string value that identifies the
  version of the metadata format.  Versions are a X.Y string where X and Y are
  integers.  A change in Y indicates a backwards-compatible change, such as a
  new optional field.  A change in X indicates a backwards-incompatible change,
  such as a renamed/removed field or a change in the meaning of a field.
"""

from __future__ import annotations

import warnings
from inspect import signature
from typing import TYPE_CHECKING, Any, Callable, cast

from ._structs import MetadataProvider

if TYPE_CHECKING:
    from typing import Protocol

    from pymmcore_plus.core import CMMCorePlus

    class MetaDataGetter(Protocol):
        """Callable that fetches metadata."""

        def __call__(self, core: CMMCorePlus, extra: dict[str, Any]) -> Any:
            """Must core and `extra` dict.

            May search for keys in `extra` to modify behavior.
            """


_METADATA_GETTERS: dict[str, dict[str, MetaDataGetter]] = {}
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
