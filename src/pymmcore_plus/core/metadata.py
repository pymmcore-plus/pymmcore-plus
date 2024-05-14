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

from contextlib import suppress
from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Mapping,
    MutableMapping,
    NotRequired,
    TypedDict,
)

from . import _state

if TYPE_CHECKING:
    from pymmcore_plus.core import CMMCorePlus

    from ._state import (
        AutoFocusDict,
        DeviceTypeDict,
        ImageDict,
        PixelSizeConfigDict,
        PositionDict,
        SystemInfoDict,
        SystemStatusDict,
    )

    class MetaDict(TypedDict, total=False):
        format: str
        version: str

    class SummaryMetaV1(MetaDict, total=False):
        Devices: dict[str, dict[str, str]]
        SystemInfo: SystemInfoDict
        SystemStatus: SystemStatusDict
        ConfigGroups: dict[str, dict[str, Any]]
        Image: ImageDict
        Position: PositionDict
        AutoFocus: AutoFocusDict
        PixelSizeConfig: dict[str, str | PixelSizeConfigDict]
        DeviceTypes: dict[str, DeviceTypeDict]
        MDASequence: NotRequired[dict]
        Time: str


class Format:
    SUMMARY_FULL = "summary"
    FRAME = "frame"


def summary_metadata_full_v1(core: CMMCorePlus) -> SummaryMetaV1:
    """Return full summary metadata for the given core."""
    return {
        "version": "1.0",
        "format": Format.SUMMARY_FULL,
        "time": datetime.now().isoformat(),
        "devices": _state.get_device_info(core),
        "properties": _state.get_device_state(core, True),
        "system_info": _state.get_system_info(core),
        # "system_status": _state.get_system_status(core),
        # "config_groups": _state.get_config_groups(core, True),
        "image": _state.get_image_info(core),
        "pixel_size_config": _state.get_pix_size_config(core),
    }


def frame_metadata_v1(core: CMMCorePlus) -> MetaDict:
    """Return metadata for a frame during an MDA for the given core."""
    extra = {}
    with suppress(RuntimeError):
        extra["XPositionUm"] = core.getXPosition()
        extra["YPositionUm"] = core.getYPosition()
    with suppress(RuntimeError):
        extra["ZPositionUm"] = core.getZPosition()
    return {
        "format": Format.FRAME,
        "version": "1.0",
        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
        "ExposureMs": core.getExposure(),  # type: ignore [typeddict-item]
        "PixelSizeUm": core.getPixelSizeUm(True),  # true == cached
        **extra,  # type: ignore [typeddict-item]
    }


GET_META: Mapping[str, Mapping[str, Callable[[CMMCorePlus], MutableMapping]]] = {
    Format.SUMMARY_FULL: {"1.0": summary_metadata_full_v1},
    Format.FRAME: {"1.0": frame_metadata_v1},
}


def get_metadata_function(
    format: str | None = None, version: str = "1.0"
) -> Callable[[CMMCorePlus], MutableMapping]:
    """Return a function that can fetch metadata in the specified format and version."""
    fmt = format or Format.SUMMARY_FULL
    if "." not in version and len(version) == 1:
        version += ".0"

    try:
        return GET_META[fmt][version]
    except KeyError:
        options = ", ".join(
            f"{fmt}/{ver}" for fmt, versions in GET_META.items() for ver in versions
        )
        raise ValueError(
            f"Unsupported metadata format/version: {fmt}/{version}. Options: {options}"
        ) from None
