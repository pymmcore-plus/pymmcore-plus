from __future__ import annotations

from typing import TYPE_CHECKING

from ._base import MetadataProvider, ensure_valid_metadata_func, get_metadata_func
from ._legacy import LegacyFrameMeta, LegacySummaryMeta
from ._structs import FrameMetaStructV1, SummaryMetaStructV1

if TYPE_CHECKING:
    from ._base import MetaDataGetter as MetaDataGetter

__all__ = [
    "MetadataProvider",
    "get_metadata_func",
    "ensure_valid_metadata_func",
    "LegacySummaryMeta",
    "LegacyFrameMeta",
    "SummaryMetaStructV1",
    "FrameMetaStructV1",
]
