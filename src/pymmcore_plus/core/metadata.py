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

from typing import TYPE_CHECKING, Callable, Mapping

from ._structs import Format, FrameMetaV1, PyMMCoreStruct, SummaryMetaV1

if TYPE_CHECKING:
    from pymmcore_plus.core import CMMCorePlus

    MetaDataGetter = Callable[[CMMCorePlus], PyMMCoreStruct]


_METADATA_GETTERS: Mapping[str, Mapping[str, MetaDataGetter]] = {
    Format.SUMMARY_FULL: {"1.0": SummaryMetaV1.from_core},
    Format.FRAME: {"1.0": FrameMetaV1.from_core},
}


def get_metadata_func(
    format: str | None = None, version: str = "1.0"
) -> MetaDataGetter:
    """Return a function that can fetch metadata in the specified format and version."""
    fmt = format or Format.SUMMARY_FULL
    if "." not in version and len(version) == 1:
        version += ".0"

    try:
        return _METADATA_GETTERS[fmt][version]
    except KeyError:
        options = ", ".join(
            f"{fmt}/{ver}"
            for fmt, versions in _METADATA_GETTERS.items()
            for ver in versions
        )
        raise ValueError(
            f"Unsupported metadata format/version: {fmt}/{version}. Options: {options}"
        ) from None
