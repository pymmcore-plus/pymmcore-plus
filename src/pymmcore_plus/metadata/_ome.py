from __future__ import annotations

import uuid
from contextlib import suppress
from datetime import datetime
from typing import TYPE_CHECKING, NamedTuple

import useq
from ome_types.model import (
    OME,
    Channel,
    Image,
    ImageRef,
    Instrument,
    Pixels,
    Pixels_DimensionOrder,
    PixelType,
    Plane,
    Plate,
    TiffData,
    UnitsLength,
    UnitsTime,
    Well,
    WellSample,
)

from pymmcore_plus.mda._runner import GeneratorMDASequence

if TYPE_CHECKING:
    from pymmcore_plus.metadata.schema import ImageInfo

    from .schema import FrameMetaV1, SummaryMetaV1


__all__ = ["create_ome_metadata"]


def create_ome_metadata(
    summary_metadata: SummaryMetaV1, frame_metadata_list: list[FrameMetaV1]
) -> OME:
    """Create OME metadata from metadata saved as json by the core engine.

    Parameters
    ----------
    summary_metadata : SummaryMetaV1
        Summary metadata containing acquisition information.
    frame_metadata_list : list[FrameMetaV1]
        List of frame metadata for each acquired image.

    Returns
    -------
    OME
        The OME metadata as an `ome_types.OME` object.
    """
    _uuid = f"urn:uuid:{uuid.uuid4()}"
    ome = OME(uuid=_uuid)

    ome.instruments = instruments = _build_instrument_list(summary_metadata)

    image_infos = summary_metadata.get("image_infos", ())
    if not frame_metadata_list or not image_infos:
        return ome

    sequence = _extract_mda_sequence(summary_metadata, frame_metadata_list[0])
    position_groups = _group_frames_by_position(frame_metadata_list)
    images = _build_ome_images(
        dimension_info=_extract_dimension_info(image_infos[0]),
        sequence=sequence,
        position_groups=position_groups,
        acquisition_date=_extract_acquisition_date(summary_metadata),
    )

    plates = []
    if (plate_plan := _extract_plate_plan(sequence)) is not None:
        position_to_image_mapping = _create_position_to_image_mapping(position_groups)
        plates = [_build_ome_plate(plate_plan, position_to_image_mapping)]

    return OME(
        uuid=_uuid,
        images=images,
        instruments=instruments,
        plates=plates,
    )


# =============================================================================
# Data Structures
# =============================================================================


class _DimensionInfo(NamedTuple):
    pixel_size_um: float
    dtype: str | None
    height: int
    width: int


class _PositionKey(NamedTuple):
    name: str | None
    p_index: int
    g_index: int | None = None

    def __str__(self) -> str:
        p_name = self.name or f"Pos{self.p_index:04d}"
        if self.g_index is not None:
            return f"{p_name}_Grid{self.g_index:04d}_{self.p_index}"
        else:
            return f"{p_name}_{self.p_index}"

    @property
    def image_id(self) -> str:
        if self.g_index is not None:
            return f"{self.p_index}_{self.g_index}"
        return f"{self.p_index}"


# =============================================================================
# Metadata Extraction Functions
# =============================================================================


def _extract_dimension_info(
    image_info: ImageInfo,
) -> _DimensionInfo:
    """Extract pixel size (µm), data type, width, and height from image_infos."""
    return _DimensionInfo(
        pixel_size_um=image_info.get("pixel_size_um", 1.0),
        dtype=image_info.get("dtype", None),
        width=image_info.get("width", 0),
        height=image_info.get("height", 0),
    )


def _extract_acquisition_date(summary_metadata: SummaryMetaV1) -> datetime | None:
    """Extract acquisition date from summary metadata."""
    if (acquisition_time := summary_metadata.get("datetime")) is not None:
        with suppress(ValueError, AttributeError):
            return datetime.fromisoformat(acquisition_time.replace("Z", "+00:00"))
    return None


def _extract_mda_sequence(
    summary_metadata: SummaryMetaV1, single_frame_metadata: FrameMetaV1
) -> useq.MDASequence | None:
    """Extract the MDA sequence from summary metadata or frame metadata."""
    if (sequence_data := summary_metadata.get("mda_sequence")) is not None:
        return useq.MDASequence.model_validate(sequence_data)
    if (mda_event := _extract_mda_event(single_frame_metadata)) is not None:
        return mda_event.sequence
    return None


def _extract_mda_event(frame_metadata: FrameMetaV1) -> useq.MDAEvent | None:
    """Extract the useq.MDAEvent from frame metadata."""
    if (mda_event_data := frame_metadata.get("mda_event")) is not None:
        return useq.MDAEvent.model_validate(mda_event_data)
    return None  # pragma: no cover


def _extract_plate_plan(
    sequence: useq.MDASequence | None,
) -> useq.WellPlatePlan | None:
    """Extract the plate plan from the MDA sequence if it exists."""
    if sequence is None:  # pragma: no cover
        return None
    stage_positions = sequence.stage_positions
    if isinstance(stage_positions, useq.WellPlatePlan):
        return stage_positions
    return None


# =============================================================================
# Frame Grouping and Processing
# =============================================================================


def _group_frames_by_position(
    frame_metadata_list: list[FrameMetaV1],
) -> dict[_PositionKey, list[FrameMetaV1]]:
    """Reorganize frame metadata by stage position index in a dictionary.

    Handles the 'g' axis (grid) by converting it to separate positions,
    since OME doesn't support the 'g' axis. Each grid position becomes
    a separate OME Image with names like "Pos0000_Grid0000".

    Returns
    -------
    dict[str, list[FrameMetaV1]]
        mapping of position identifier (e.g. 'Pos0000_Grid0000')
        to list of `FrameMetaV1`.
    """
    frames_by_position: dict[_PositionKey, list[FrameMetaV1]] = {}
    for frame_metadata in frame_metadata_list:
        if (mda_event := _extract_mda_event(frame_metadata)) is None:
            continue  # pragma: no cover

        p_index = mda_event.index.get(useq.Axis.POSITION, 0) or 0
        g_index = mda_event.index.get(useq.Axis.GRID, None)
        key = _PositionKey(mda_event.pos_name, p_index, g_index)
        pos_list = frames_by_position.setdefault(key, [])
        pos_list.append(frame_metadata)
    return frames_by_position


def _create_position_to_image_mapping(
    position_groups: dict[_PositionKey, list[FrameMetaV1]],
) -> dict[int, str]:
    """Create a mapping from position index to image ID."""
    position_to_image_mapping: dict[int, str] = {}

    for position_key, position_frames in position_groups.items():
        if position_frames:
            mda_event = _extract_mda_event(position_frames[0])
            if mda_event is not None:
                position_index = mda_event.index.get("p", 0)
                position_to_image_mapping[position_index] = position_key.image_id
    return position_to_image_mapping


# =============================================================================
# Dimension Order and Pixel Information
# =============================================================================


def _determine_dimension_order(
    sequence: useq.MDASequence | None,
) -> Pixels_DimensionOrder | None:
    """Determine the dimension order for pixels."""
    if sequence is None or isinstance(sequence, GeneratorMDASequence):
        return Pixels_DimensionOrder.XYTCZ
    return _extract_dimension_order_from_sequence(sequence)


def _extract_dimension_order_from_sequence(
    sequence: useq.MDASequence,
) -> Pixels_DimensionOrder:
    """Extract axis order from a useq.MDASequence.

    Returns
    -------
    A Pixels_DimensionOrder representing the dimension order compatible with OME
    standards
    (e.g., "XYCZT").
    """
    filtered_axes = (axis for axis in sequence.axis_order if axis not in {"p", "g"})
    dimension_order = "XY" + "".join(filtered_axes).upper()

    if len(dimension_order) != 5:
        missing_axes = [axis for axis in "XYCZT" if axis not in dimension_order]
        dimension_order += "".join(missing_axes)

    return Pixels_DimensionOrder(dimension_order)


def _extract_pixel_dimensions_and_channels(
    sequence: useq.MDASequence | None,
    position_frames: list[FrameMetaV1],
    image_id: str,
) -> tuple[tuple[int, int, int], list[Channel]]:
    """Extract pixel dimensions and channels from sequence or frames."""
    if sequence is None or isinstance(sequence, GeneratorMDASequence):
        return _extract_pixel_info_from_frames(position_frames, image_id)
    return _extract_pixel_info_from_sequence(sequence, image_id)


def _extract_pixel_info_from_frames(
    position_metadata: list[FrameMetaV1],
    image_id: str,
) -> tuple[tuple[int, int, int], list[Channel]]:
    """Extract pixel dimensions and channel information from frame metadata.

    Returns
    -------
        A tuple containing the maximum (t, z, c) dimensions, and a list of channels.
    """
    max_t, max_z, max_c = 0, 0, 0
    channels: dict[int, Channel] = {}

    for frame_metadata in position_metadata:
        mda_event = _extract_mda_event(frame_metadata)
        if mda_event is None:  # pragma: no cover
            continue

        t_index = mda_event.index.get("t", 0)
        z_index = mda_event.index.get("z", 0)
        c_index = mda_event.index.get("c", 0)

        max_t = max(max_t, t_index)
        max_z = max(max_z, z_index)
        max_c = max(max_c, c_index)

        if c_index not in channels and mda_event.channel is not None:
            channels[c_index] = Channel(
                id=f"Channel:{image_id}:{c_index}",
                name=mda_event.channel.config,
                samples_per_pixel=1,
            )

    sorted_channels = [channels[i] for i in sorted(channels.keys())]
    return (max_t + 1, max_z + 1, max_c + 1), sorted_channels


def _extract_pixel_info_from_sequence(
    sequence: useq.MDASequence,
    image_id: str,
) -> tuple[tuple[int, int, int], list[Channel]]:
    """Extract pixel dimensions and channel information from MDA sequence."""
    max_t = sequence.sizes.get("t", 1)
    max_z = sequence.sizes.get("z", 1)
    channels = [
        Channel(
            id=f"Channel:{image_id}:{index}",
            name=channel.config,
            samples_per_pixel=1,
        )
        for index, channel in enumerate(sequence.channels)
    ]
    return (max_t, max_z, len(channels)), channels


# =============================================================================
# OME Object Builders
# =============================================================================


def _build_ome_images(
    dimension_info: _DimensionInfo,
    sequence: useq.MDASequence | None,
    position_groups: dict[_PositionKey, list[FrameMetaV1]],
    acquisition_date: datetime | None,
) -> list[Image]:
    """Build OME Images from grouped frame metadata by position."""
    images = []
    for position_key, position_frames in position_groups.items():
        image_id = position_key.image_id
        position_name = str(position_key)

        dimension_order = _determine_dimension_order(sequence)
        if not dimension_order:  # pragma: no cover
            continue

        size_info, channels = _extract_pixel_dimensions_and_channels(
            sequence, position_frames, image_id
        )
        max_t, max_z, max_c = size_info

        pixels = _build_pixels_object(
            image_id,
            dimension_order,
            dimension_info,
            max_t,
            max_z,
            max_c,
            channels,
            position_frames,
        )

        image = Image(
            acquisition_date=acquisition_date,
            id=f"Image:{image_id}",
            name=position_name,
            pixels=pixels,
        )
        images.append(image)
    return images


def _build_pixels_object(
    image_id: str,
    dimension_order: Pixels_DimensionOrder,
    dimension_info: _DimensionInfo,
    max_t: int,
    max_z: int,
    max_c: int,
    channels: list[Channel],
    position_frames: list[FrameMetaV1],
) -> Pixels:
    """Build a Pixels object with the given parameters."""
    return Pixels(
        id=f"Pixels:{image_id}",
        dimension_order=dimension_order,
        size_x=dimension_info.width,
        size_y=dimension_info.height,
        size_z=max(max_z, 1),
        size_c=max(max_c, 1),
        size_t=max(max_t, 1),
        type=PixelType(dimension_info.dtype),
        physical_size_x=dimension_info.pixel_size_um,
        physical_size_x_unit=UnitsLength.MICROMETER,
        physical_size_y=dimension_info.pixel_size_um,
        physical_size_y_unit=UnitsLength.MICROMETER,
        channels=channels,
        tiff_data_blocks=_build_tiff_data_list(position_frames),
        planes=_build_plane_list(position_frames),
    )


def _build_tiff_data_list(position_frames: list[FrameMetaV1]) -> list[TiffData]:
    """Build TiffData objects for frame metadata at a specific position."""
    tiff_data_blocks = []
    for frame_metadata in position_frames:
        mda_event = _extract_mda_event(frame_metadata)
        if mda_event is None:  # pragma: no cover
            continue

        event_index = mda_event.index
        z_index = event_index.get("z", 0)
        c_index = event_index.get("c", 0)
        t_index = event_index.get("t", 0)

        # Create a TiffData block for this plane
        tiff_data = TiffData(
            first_z=z_index,
            first_c=c_index,
            first_t=t_index,
            plane_count=1,
        )
        tiff_data_blocks.append(tiff_data)

    return tiff_data_blocks


def _build_plane_list(position_frames: list[FrameMetaV1]) -> list[Plane]:
    """Build Plane objects for frame metadata at a specific position."""
    planes = []
    for frame_metadata in position_frames:
        mda_event = _extract_mda_event(frame_metadata)
        if mda_event is None:  # pragma: no cover
            continue

        event_index = mda_event.index
        z_index = event_index.get("z", 0)
        c_index = event_index.get("c", 0)
        t_index = event_index.get("t", 0)

        runner_time_ms = frame_metadata.get("runner_time_ms", 0.0)
        delta_t = runner_time_ms / 1000.0 if runner_time_ms > 0 else None
        exposure_ms = frame_metadata.get("exposure_ms", 0.0)

        plane = Plane(
            the_z=z_index,
            the_c=c_index,
            the_t=t_index,
            position_x=mda_event.x_pos,
            position_x_unit=UnitsLength.MICROMETER,
            position_y=mda_event.y_pos,
            position_y_unit=UnitsLength.MICROMETER,
            position_z=mda_event.z_pos,
            position_z_unit=UnitsLength.MICROMETER,
            delta_t=delta_t,
            delta_t_unit=UnitsTime.SECOND,
            exposure_time=exposure_ms,
            exposure_time_unit=UnitsTime.MILLISECOND,
        )

        planes.append(plane)
    return planes


def _build_ome_plate(
    plate_plan: useq.WellPlatePlan, position_to_image_mapping: dict[int, str]
) -> Plate:
    """Create a Plate object from a useq.WellPlatePlan."""
    wells: list[Well] = []

    # create a mapping from well name to acquisition indices
    well_acquisition_map: dict[str, list[int]] = {}
    for acquisition_index, position in enumerate(plate_plan.image_positions):
        well_name = position.name
        if well_name is not None:
            if well_name not in well_acquisition_map:
                well_acquisition_map[well_name] = []
            well_acquisition_map[well_name].append(acquisition_index)

    for (row, col), name, pos in zip(
        plate_plan.selected_well_indices,
        plate_plan.selected_well_names,
        plate_plan.selected_well_positions,
    ):
        # get all acquisition indices for this well
        acquisition_indices = well_acquisition_map.get(name, [])

        # create WellSample objects for each acquisition in this well
        well_samples = []
        for acq_index in acquisition_indices:
            # Use the actual image ID from the mapping
            image_id = position_to_image_mapping.get(acq_index, str(acq_index))
            well_samples.append(
                WellSample(
                    id=f"WellSample:{acq_index}",
                    position_x=pos.x,
                    position_y=pos.y,
                    position_x_unit=UnitsLength.MICROMETER,
                    position_y_unit=UnitsLength.MICROMETER,
                    index=acq_index,
                    image_ref=ImageRef(id=f"Image:{image_id}"),
                )
            )

        wells.append(
            Well(
                row=row,
                column=col,
                well_samples=well_samples,
            )
        )

    return Plate(
        name=plate_plan.plate.name,
        rows=plate_plan.plate.rows,
        columns=plate_plan.plate.columns,
        wells=wells,
        well_origin_x=plate_plan.a1_center_xy[0],
        well_origin_x_unit=UnitsLength.MICROMETER,
        well_origin_y=plate_plan.a1_center_xy[1],
        well_origin_y_unit=UnitsLength.MICROMETER,
    )


def _build_instrument_list(summary_metadata: SummaryMetaV1) -> list[Instrument]:
    """Build instrument list from summary metadata."""
    # TODO
    return []
