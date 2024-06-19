from __future__ import annotations

import time
from contextlib import suppress
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pymmcore_plus.core._constants import PixelType

from ._base import MetadataProvider

if TYPE_CHECKING:
    from typing import Literal

    from pymmcore_plus import CMMCorePlus


class LegacySummaryMeta(MetadataProvider):
    @classmethod
    def provider_key(cls) -> str:
        return "legacy"

    @classmethod
    def provider_version(cls) -> str:
        return "1.0"

    @classmethod
    def metadata_type(cls) -> Literal["summary"]:
        return "summary"

    @classmethod
    def from_core(cls, core: CMMCorePlus, extra: dict[str, Any]) -> Any:
        """Get the summary metadata for the sequence."""
        pt = PixelType.for_bytes(core.getBytesPerPixel(), core.getNumberOfComponents())
        affine = core.getPixelSizeAffine(True)  # true == cached

        return {
            "DateAndTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
            "PixelType": str(pt),
            "PixelSize_um": core.getPixelSizeUm(),
            "PixelSizeAffine": ";".join(str(x) for x in affine),
            "Core-XYStage": core.getXYStageDevice(),
            "Core-Focus": core.getFocusDevice(),
            "Core-Autofocus": core.getAutoFocusDevice(),
            "Core-Camera": core.getCameraDevice(),
            "Core-Galvo": core.getGalvoDevice(),
            "Core-ImageProcessor": core.getImageProcessorDevice(),
            "Core-SLM": core.getSLMDevice(),
            "Core-Shutter": core.getShutterDevice(),
            "AffineTransform": "Undefined",
        }


class LegacyFrameMeta(MetadataProvider):
    @classmethod
    def provider_key(cls) -> str:
        return "legacy"

    @classmethod
    def provider_version(cls) -> str:
        return "1.0"

    @classmethod
    def metadata_type(cls) -> Literal["frame"]:
        return "frame"

    @classmethod
    def from_core(cls, core: CMMCorePlus, extra: dict[str, Any]) -> Any:
        tags = extra
        for dev, label, val in core.getSystemStateCache():
            tags[f"{dev}-{label}"] = val

        # these are added by AcqEngJ
        # yyyy-MM-dd HH:mm:ss.mmmmmm  # NOTE AcqEngJ omits microseconds
        tags["Time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        tags["PixelSizeUm"] = core.getPixelSizeUm(True)  # true == cached
        with suppress(RuntimeError):
            tags["XPositionUm"] = core.getXPosition()
            tags["YPositionUm"] = core.getYPosition()
        with suppress(RuntimeError):
            tags["ZPositionUm"] = core.getZPosition()

        # used by Runner
        tags["PerfCounter"] = time.perf_counter()
        return tags
