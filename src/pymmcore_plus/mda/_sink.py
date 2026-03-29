from __future__ import annotations

import json
import warnings
from typing import TYPE_CHECKING, Any, Protocol, cast

from ome_writers import (
    AcquisitionSettings,
    Dimension,
    create_stream,
    useq_to_acquisition_settings,
)
from pydantic import BaseModel

from pymmcore_plus._logger import logger
from pymmcore_plus.mda._generator_sequence import GeneratorMDASequence

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    import numpy as np
    import ome_types.model as ome
    from ome_writers import OMEStream
    from ome_writers._useq import AcquisitionSettingsDict
    from useq import MDAEvent, MDASequence

    from pymmcore_plus.mda._runner import DimensionOverride, SinkView
    from pymmcore_plus.metadata.schema import FrameMetaV1, SummaryMetaV1


class SinkProtocol(Protocol):
    def setup(self, sequence: MDASequence, meta: SummaryMetaV1 | None) -> None: ...
    def append(self, img: np.ndarray, event: MDAEvent, meta: FrameMetaV1) -> None: ...
    def skip(self, *, frames: int = 1) -> None: ...
    def close(self) -> None: ...
    def get_view(self) -> SinkView | None: ...


class OmeWritersSink(SinkProtocol):
    """Our default built-in data sink.

    uses ome-writers to write to OME-Zarr or OME-TIFF, or scratch (tmp/memory).
    """

    def __init__(
        self,
        settings: AcquisitionSettings,
        dimension_overrides: dict[str, DimensionOverride] | None = None,
    ) -> None:
        self._settings = settings
        self._dimension_overrides = dimension_overrides or {}
        self._stream: OMEStream | None = None
        self._summary_meta: SummaryMetaV1 | None = None

    @classmethod
    def from_output(
        cls,
        output: str | Path | AcquisitionSettings,
        overwrite: bool = False,
        dimension_overrides: dict[str, DimensionOverride] | None = None,
    ) -> OmeWritersSink:
        if isinstance(output, AcquisitionSettings):
            return cls(output, dimension_overrides=dimension_overrides)
        stripped = str(output).rstrip("/").rstrip(":").lower()
        if stripped in ("memory", "scratch"):
            return cls(
                AcquisitionSettings(format="scratch", overwrite=overwrite),  # pyright: ignore
                dimension_overrides=dimension_overrides,
            )
        return cls(
            AcquisitionSettings(root_path=str(output), overwrite=overwrite),
            dimension_overrides=dimension_overrides,
        )

    def setup(self, sequence: MDASequence, meta: SummaryMetaV1 | None) -> None:
        # FIXME?
        # I'm not sure it's possible to abstract this enough to work with
        # arbitrary engines... this is a tight coupling that will probably just
        # exist for a long time
        if not meta:  # pragma: no cover
            raise NotImplementedError(
                "Cannot use output sinks without summary metadaata "
                "from the engine's setup_sequence method."
            )

        # fixme... image infos might not be locked down enough (it's a list...)
        info = meta["image_infos"][0]
        width, height = info["width"], info["height"]
        pixel_size_um = info["pixel_size_um"]

        useq_settings: Mapping
        if isinstance(sequence, GeneratorMDASequence):
            useq_settings = _unbounded_3d_settings(width, height, pixel_size_um)
        else:
            try:
                useq_settings = useq_to_acquisition_settings(
                    sequence,
                    image_width=width,
                    image_height=height,
                    pixel_size_um=pixel_size_um,
                )
            except NotImplementedError as e:
                logger.warning(
                    "Could not convert MDASequence to AcquisitionSettings: %s. "
                    "Falling back to generic unbounded 3D settings.",
                    e,
                )
                useq_settings = _unbounded_3d_settings(width, height, pixel_size_um)

        # Apply dimension overrides (chunk_size, shard_size_chunks) to all paths
        if overrides := self._dimension_overrides:
            dims = list(useq_settings["dimensions"])
            for i, dim in enumerate(dims):
                if dim.name in overrides:
                    dims[i] = dim.model_copy(update=overrides[dim.name])
            useq_settings["dimensions"] = dims

        # multi-camera: add a camera dimension before Y/X so the sink
        # expects N_events * N_cameras frames instead of just N_events
        n_cameras = info.get("num_camera_adapter_channels", 1)
        if n_cameras > 1:
            if sequence.channels:
                warnings.warn(
                    "Multi-camera acquisition combined with MDASequence channels "
                    "is not fully supported: OME metadata will only reflect the "
                    "optical channel names, not the per-camera axis.",
                    stacklevel=2,
                )
            dims = list(useq_settings["dimensions"])
            cam_dim = Dimension(name="cam", count=n_cameras, type="other")
            # insert before Y, X (the last two dimensions)
            dims.insert(len(dims) - 2, cam_dim)
            useq_settings = {**useq_settings, "dimensions": dims}

        new_settings = {
            **self._settings.model_dump(),
            **useq_settings,
            "dtype": info["dtype"],
        }
        self._settings = AcquisitionSettings.model_validate(new_settings)
        self._stream = create_stream(self._settings)
        self._summary_meta = meta
        self._write_summary_metadata()

    def append(self, img: np.ndarray, event: MDAEvent, meta: FrameMetaV1) -> None:
        self._stream.append(img, frame_metadata=_frame_meta_to_ome(meta))  # type: ignore[union-attr]

    def skip(self, *, frames: int = 1) -> None:
        self._stream.skip(frames=frames)  # type: ignore[union-attr]

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._write_summary_metadata(after_close=True)

    def get_view(self) -> SinkView | None:
        if self._stream is None:
            return None
        return self._stream.view(dynamic_shape=True, strict=False)

    def _write_summary_metadata(self, *, after_close: bool = False) -> None:
        """Write summary metadata to the stream in a format-aware way.

        For OME-Zarr this is called immediately after stream creation.
        For OME-TIFF this must be called after close (TIFF requires finalization
        before metadata can be updated).
        """
        if self._stream is None or self._summary_meta is None:
            return

        fmt = self._settings.format.name
        if fmt == "ome-zarr" and not after_close:
            summary_dict = _serialize_summary_meta(self._summary_meta)
            zarr_meta = cast("dict[str, dict]", self._stream.get_metadata())
            try:
                for _path, attrs in zarr_meta.items():
                    attrs.setdefault("pymmcore_plus", {})["summary_metadata"] = (
                        summary_dict
                    )
                self._stream.update_metadata(zarr_meta)
            except Exception as e:
                logger.warning(
                    "Failed to add summary metadata to OME-Zarr: %s", e, exc_info=True
                )

        elif fmt == "ome-tiff" and after_close:
            summary_dict = _serialize_summary_meta(self._summary_meta)
            tiff_meta = cast("dict[int, ome.OME]", self._stream.get_metadata())
            try:
                _enrich_tiff_with_summary(tiff_meta, summary_dict)
                self._stream.update_metadata(tiff_meta)
            except Exception as e:
                logger.warning(
                    "Failed to add summary metadata to OME-TIFF: %s", e, exc_info=True
                )


def _unbounded_3d_settings(
    width: int, height: int, pixel_size_um: float | None = None
) -> AcquisitionSettingsDict:
    """Return generic unbounded 3D acquisition settings (t, y, x).

    Used as a fallback when a sequence can't be converted to ome-writers dimensions.
    """
    return {
        "dimensions": [
            Dimension(name="t", count=None, chunk_size=1, type="time"),
            Dimension(
                name="y",
                count=height,
                chunk_size=height,
                scale=pixel_size_um,
                unit="micrometer",
            ),
            Dimension(
                name="x",
                count=width,
                chunk_size=width,
                scale=pixel_size_um,
                unit="micrometer",
            ),
        ],
        "plate": None,
    }


def _frame_meta_to_ome(meta: FrameMetaV1) -> dict:
    """Convert FrameMetaV1 to ome-writers frame_metadata dict."""
    # TODO:
    # decide whether we should be passing *everything* else from FrameMetaV1
    # after converting/popping a few special keys...
    d: dict = {
        "delta_t": meta["runner_time_ms"] / 1000,
        "exposure_time": meta["exposure_ms"] / 1000,
    }
    if pos := meta.get("position"):
        d.update({f"position_{k}": v for k, v in pos.items() if k in "xyz"})
    return d


def _serialize_summary_meta(meta: SummaryMetaV1) -> dict[str, Any]:
    """Convert SummaryMetaV1 to a JSON-serializable dict."""
    d = dict(meta)
    if (seq := meta.get("mda_sequence")) and isinstance(seq, BaseModel):
        d["mda_sequence"] = seq.model_dump(mode="json", exclude_unset=True)
    return d


def _enrich_tiff_with_summary(
    metadata: Mapping[int, ome.OME], summary_dict: dict[str, Any]
) -> None:
    """Add summary metadata to OME-TIFF as MapAnnotations."""
    import ome_types.model as ome

    summary_json = json.dumps(summary_dict)

    for _pos_idx, ome_model in metadata.items():
        if not ome_model.structured_annotations:
            ome_model.structured_annotations = ome.StructuredAnnotations()

        annotation = ome.MapAnnotation(
            namespace="pymmcore_plus",
            value={"summary_metadata_json": summary_json},  # pyright: ignore
        )
        ome_model.structured_annotations.map_annotations.append(annotation)


# # If we ever to output actual XML metadata instead of JSON blobs,
# # it would look like this:
#
# summary_xml = _dict_to_xml({"pymmcore_plus": {"summary_metadata": summary_dict}})
# for _pos_idx, ome_model in metadata.items():
#     if not ome_model.structured_annotations:
#         ome_model.structured_annotations = ome.StructuredAnnotations()
#     annotation = ome.XMLAnnotation(value=summary_xml)  # type: ignore
#     ome_model.structured_annotations.xml_annotations.append(annotation)
#
# def _dict_to_xml(d: dict, root_tag: str = "data") -> str:
#     try:
#         from lxml.etree import Element, tostring
#     except ImportError:
#         from xml.etree.ElementTree import Element, tostring

#     _SINGULAR = {"properties": "property"}

#     def _build(parent: Element, obj: object) -> None:
#         if isinstance(obj, dict):
#             for k, v in obj.items():
#                 child = Element(k)
#                 parent.append(child)
#                 _build(child, v)
#         elif isinstance(obj, (list, tuple)):
#             # Use singular of parent tag as item wrapper, or "item"
#             tag = _SINGULAR.get(
#                 parent.tag,
#                 parent.tag.rstrip("s") if parent.tag.endswith("s") else "item",
#             )
#             for item in obj:
#                 child = Element(tag)
#                 parent.append(child)
#                 _build(child, item)
#         else:
#             parent.text = str(obj)

#     root = Element(root_tag)
#     _build(root, d)
#     return tostring(root, encoding="unicode")
