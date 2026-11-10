from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from ome_writers import (
    AcquisitionSettings,
    Channel,
    Dimension,
    create_stream,
    useq_to_acquisition_settings,
)
from pydantic import BaseModel

from pymmcore_plus._logger import logger
from pymmcore_plus.mda._generator_sequence import GeneratorMDASequence

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    import numpy as np
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
        # set for multi-camera runs: puts frames into the folded channel order
        self._reorder: _FrameReorderer | None = None

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

        # multi-camera: every event yields one frame per physical camera. OME allows
        # at most 5 non-position axes (t, c, z, y, x), so instead of a separate camera
        # axis the cameras are folded into the channel axis (channels x cameras).
        self._reorder = None
        n_cameras = info.get("num_camera_adapter_channels", 1)
        if n_cameras > 1:
            cameras = list(
                info.get("camera_channel_names")
                or [f"cam{i}" for i in range(n_cameras)]
            )
            dims, self._reorder = _fold_cameras_into_channels(
                list(useq_settings["dimensions"]), cameras
            )
            useq_settings = {**useq_settings, "dimensions": dims}

        new_settings = {
            **self._settings.model_dump(),
            **useq_settings,
            "dtype": info["dtype"],
        }
        self._settings = AcquisitionSettings.model_validate(new_settings)
        self._stream = create_stream(self._settings)
        self._summary_meta = meta
        self._set_summary_metadata()

    def append(self, img: np.ndarray, event: MDAEvent, meta: FrameMetaV1) -> None:
        frame_meta = _frame_meta_to_ome(meta)
        if self._reorder is not None:
            self._reorder.push(self._stream, img, frame_meta)  # type: ignore[arg-type]
        else:
            self._stream.append(img, frame_metadata=frame_meta)  # type: ignore[union-attr]

    def skip(self, *, frames: int = 1) -> None:
        if self._reorder is not None:
            for _ in range(frames):
                self._reorder.push(self._stream, None, None)  # type: ignore[arg-type]
        else:
            self._stream.skip(frames=frames)  # type: ignore[union-attr]

    def close(self) -> None:
        if self._stream is not None:
            if self._reorder is not None:
                self._reorder.flush(self._stream)
            self._stream.close()

    def get_view(self) -> SinkView | None:
        if self._stream is None:
            return None
        return self._stream.view(dynamic_shape=True, strict=False)

    def _set_summary_metadata(self) -> None:
        """Attach acquisition-level summary metadata to the stream.

        Delegates to `OMEStream.set_global_metadata`. Where the payload
        lands on disk is format-defined: parent root group for OME-Zarr,
        canonical metadata file for single-file / master-tiff / companion-file
        OME-TIFF, or every per-position file for OME-TIFF `redundant` mode.
        """
        if self._stream is None or self._summary_meta is None:
            return

        payload = {"summary_metadata": _serialize_summary_meta(self._summary_meta)}
        try:
            self._stream.set_global_metadata("pymmcore_plus", payload)
        except Exception as e:
            logger.warning("Failed to attach summary metadata: %s", e, exc_info=True)


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


def _channel_name(coord: Any, idx: int) -> str:
    if isinstance(coord, Channel):
        return coord.name
    return str(coord) if coord is not None else f"c{idx}"


def _fold_cameras_into_channels(
    dims: list[Dimension], cameras: list[str]
) -> tuple[list[Dimension], _FrameReorderer]:
    """Fold the per-event camera axis of a multi-camera run into the channel axis.

    Frames arrive in the order of `dims` with the camera innermost (each event
    yields one frame per camera). They are stored with a single channel axis of
    `n_channels * n_cameras` entries named `<channel>-<camera>`, as Micro-Manager
    names them, in place of the original channel axis -- or, without channels, a
    new one named after the cameras, placed before the first spatial index axis
    (z), as OME requires. Returns the storage dimensions and the reorderer that
    maps arrival order to storage order.
    """
    *index_dims, y_dim, x_dim = dims
    n_cam = len(cameras)

    c_idx = next(
        (
            i
            for i, d in enumerate(index_dims)
            if d.type == "channel" or (d.type is None and d.name == "c")
        ),
        None,
    )
    if c_idx is not None:
        c_dim = index_dims[c_idx]
        n_ch = c_dim.count or 1
        coords = c_dim.coords or [None] * n_ch
        names = [_channel_name(c, i) for i, c in enumerate(coords)]
        folded = c_dim.model_copy(
            update={
                "count": n_ch * n_cam,
                "coords": [
                    Channel(name=f"{ch}-{cam}") for ch in names for cam in cameras
                ],
            }
        )
        insert_at = c_idx
        storage = [*index_dims[:c_idx], folded, *index_dims[c_idx + 1 :]]
    else:
        folded = Dimension(
            name="c",
            count=n_cam,
            type="channel",
            coords=[Channel(name=cam) for cam in cameras],
        )
        insert_at = next(
            (i for i, d in enumerate(index_dims) if d.type == "space"), len(index_dims)
        )
        storage = [*index_dims[:insert_at], folded, *index_dims[insert_at:]]

    arrival_counts = [d.count for d in index_dims] + [n_cam]
    storage_counts = [d.count for d in storage]

    def to_storage(k: int) -> int:
        *idx, cam = _unravel(k, arrival_counts)
        if c_idx is not None:
            new = [*idx[:c_idx], idx[c_idx] * n_cam + cam, *idx[c_idx + 1 :]]
        else:
            new = [*idx[:insert_at], cam, *idx[insert_at:]]
        return _ravel(new, storage_counts)

    return [*storage, y_dim, x_dim], _FrameReorderer(to_storage)


def _unravel(k: int, counts: list[int | None]) -> list[int]:
    """Unravel a C-order linear index. Only the first count may be None (unbounded)."""
    coords: list[int] = []
    for count in reversed(counts[1:]):
        k, rem = divmod(k, count)  # type: ignore[arg-type]
        coords.append(rem)
    coords.append(k)
    return coords[::-1]


def _ravel(coords: list[int], counts: list[int | None]) -> int:
    """Ravel C-order coordinates. Only the first count may be None (unbounded)."""
    k = 0
    for c, count in zip(coords, counts, strict=True):
        k = k * count + c if count is not None else c  # type: ignore[operator]
    return k


class _FrameReorderer:
    """Write frames that arrive in one order to a stream that expects another.

    ome-writers streams are written sequentially, in storage order. A frame that
    arrives ahead of its storage turn is held until every frame before it has been
    written (or skipped); with cameras folded into channels, that is the later
    cameras' share of each z-stack.
    """

    def __init__(self, to_storage: Callable[[int], int]) -> None:
        self._to_storage = to_storage
        self._next_arrival = 0
        self._next_storage = 0
        # storage index -> (frame, metadata), or None for a skipped frame
        self._pending: dict[int, tuple[np.ndarray, dict] | None] = {}

    def push(
        self, stream: OMEStream, frame: np.ndarray | None, frame_meta: dict | None
    ) -> None:
        """Accept the next frame in arrival order (`frame=None` skips it)."""
        idx = self._to_storage(self._next_arrival)
        self._next_arrival += 1
        self._pending[idx] = None if frame is None else (frame, frame_meta or {})
        while self._next_storage in self._pending:
            self._write(stream, self._pending.pop(self._next_storage))

    def flush(self, stream: OMEStream) -> None:
        """Write what is still held (a run that ended early), skipping the gaps."""
        for idx in sorted(self._pending):
            if idx > self._next_storage:
                stream.skip(frames=idx - self._next_storage)
                self._next_storage = idx
            self._write(stream, self._pending.pop(idx))

    def _write(self, stream: OMEStream, item: tuple[np.ndarray, dict] | None) -> None:
        if item is None:
            stream.skip(frames=1)
        else:
            stream.append(item[0], frame_metadata=item[1])
        self._next_storage += 1


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
