from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast
from venv import logger

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
    UnitsLength,
    UnitsTime,
    Well,
    WellSample,
)

from pymmcore_plus.mda._runner import GeneratorMDASequence
from pymmcore_plus.metadata.serialize import json_loads

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pymmcore_plus.metadata.schema import ImageInfo

    from .schema import FrameMetaV1, SummaryMetaV1

MDA_EVENT = "mda_event"


def create_ome_metadata(
    metadata_path: Path | str,
) -> OME:
    """Create enhanced OME metadata from summary and frame metadata collections.

    This function organizes frame metadata by position and creates separate
    Image elements for each stage position with proper plane information.

    Parameters
    ----------
    metadata_path : Path | str
        Path to the directory containing `summary_metadata.json` and
        `frames_metadata.jsonl` files.

    Returns
    -------
    OME
        The OME metadata as an `ome_types.OME` object.
    """
    if isinstance(metadata_path, str):
        metadata_path = Path(metadata_path)

    # create OME model
    ome = OME(uuid=f"urn:uuid:{uuid.uuid4()}")

    # load summary metadata
    summary_metadata = _load_summary_metadata(metadata_path)

    # get instrument information from summary metadata
    ome.instruments = _add_ome_instrument_info(summary_metadata)

    # get pixel size, image dimensions, and data type from image_infos
    image_infos: tuple[ImageInfo, ...] = summary_metadata.get("image_infos")
    if image_infos is None:
        return ome
    pixel_size_um, dtype, height, width = _get_dimension_info(image_infos)
    # cannot create Pixels without dtype
    if dtype is None:
        return ome

    # load all frame metadata from JSONL file
    frame_metadata_list = _load_frames_metadata(metadata_path)
    if not frame_metadata_list:
        return ome

    # get the MDA sequence if available
    sequence = _get_mda_sequence(summary_metadata, frame_metadata_list[0])

    # group frames by position (handling 'g' axis if present)
    positions_map = _group_frames_by_position(frame_metadata_list)

    # get acquisition date from summary metadata
    acquisition_date = _get_acquisition_date(summary_metadata)

    for key in positions_map:
        # parse position key to extract name and indices
        position_name, image_id = _parse_position_key(key)
        position_frames = positions_map[key]

        if sequence is not None:
            dimension_order = _get_dimension_order_from_sequence(sequence)
        else:
            dimension_order = _get_dimension_order_from_frames(position_frames)

        if not dimension_order:
            # cannot create Pixels without dimension order
            continue

        if sequence is None or isinstance(sequence, GeneratorMDASequence):
            (max_t, max_z, max_c), channels = _get_pixels_info(position_frames)
        else:
            (max_t, max_z, max_c), channels = _get_pixels_info_from_sequence(sequence)

        pixels = Pixels(
            id=f"Pixels:{image_id}",
            dimension_order=Pixels_DimensionOrder(dimension_order),
            size_x=width,
            size_y=height,
            size_z=max(max_z, 1),
            size_c=max(max_c, 1),
            size_t=max(max_t, 1),
            type=PixelType(dtype),
            physical_size_x=pixel_size_um,
            physical_size_x_unit=UnitsLength.MICROMETER,
            physical_size_y=pixel_size_um,
            physical_size_y_unit=UnitsLength.MICROMETER,
            channels=channels,
        )

        pixels.planes = _get_planes(position_frames)

        image = Image(
            acquisition_date=acquisition_date,
            id=f"Image:{image_id}",
            name=position_name,
            pixels=pixels,
        )

        ome.images.append(image)

    # add plate information if available
    if (
        sequence is not None
        and (stage_pos := sequence.stage_positions)
        and isinstance(stage_pos, useq.WellPlatePlan)
    ):
        ome.plates = [_get_plate(stage_pos)]

    return ome


def _load_summary_metadata(metadata_path: Path | str) -> SummaryMetaV1:
    """Load summary metadata from a JSON file."""
    if isinstance(metadata_path, str):
        metadata_path = Path(metadata_path)

    summary_metadata_file = metadata_path / "summary_metadata.json"
    if not summary_metadata_file.exists():
        return {}  # type: ignore[return-value]

    try:
        with open(summary_metadata_file, encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}  # type: ignore[return-value]
            return cast("SummaryMetaV1", json_loads(content))
    except Exception as e:
        logger.error(f"Error reading summary metadata file: {e}")
        return {}  # type: ignore[return-value]


def _load_frames_metadata(metadata_path: Path | str) -> list[FrameMetaV1]:
    """Load all frame metadata from a JSONL file."""
    if isinstance(metadata_path, str):
        metadata_path = Path(metadata_path)

    frame_metadata_file = metadata_path / "frames_metadata.jsonl"
    if not frame_metadata_file.exists():
        return []

    frame_metadata_list: list[FrameMetaV1] = []
    try:
        with open(frame_metadata_file, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    frame_metadata_list.append(cast("FrameMetaV1", json_loads(line)))
                except Exception as e:
                    msg = (
                        f"Warning: Failed to parse line {line_num} "
                        f"in frame metadata: {e}"
                    )
                    logger.warning(msg)
                    continue
    except Exception as e:
        logger.error(f"Error reading frame metadata file: {e}")
        return []

    return frame_metadata_list


def _get_mda_sequence(
    summary_metadata: SummaryMetaV1, single_frame_metadata: FrameMetaV1
) -> useq.MDASequence | None:
    """Get the MDA sequence from summary metadata or frame metadata."""
    # get the mda_sequence from summary metadata
    seq = summary_metadata.get("mda_sequence")
    if seq is not None:
        if not isinstance(seq, useq.MDASequence):
            seq = useq.MDASequence(**seq)
        return seq
    # if is not there try form single_frame_metadata useq.MDAEvent
    ev = _get_mda_event(single_frame_metadata)
    if ev is None:
        return None
    return ev.sequence


def _get_plate(plate_plan: useq.WellPlatePlan) -> Plate:
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
            well_samples.append(
                WellSample(
                    id=f"WellSample:{acq_index}",
                    position_x=pos.x,
                    position_y=pos.y,
                    position_x_unit=UnitsLength.MICROMETER,
                    position_y_unit=UnitsLength.MICROMETER,
                    index=acq_index,
                    image_ref=ImageRef(id=f"Image:{acq_index - 1}"),
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


def _add_ome_instrument_info(summary_meta: SummaryMetaV1) -> list[Instrument]:
    """Add instrument information to the OME model based on summary metadata."""
    # TODO: use devices to get info about microscope
    # create instrument information

    # instrument = None
    # microscope_device = None
    # camera_device = None

    # devices = summary_meta[DEVICES]
    # for device in devices:
    #     if ...
    #        microscope_device = ...
    #     if ...

    # if microscope_device:
    #     microscope = Microscope(
    #             manufacturer=microscope_device.get("description", "Unknown"),
    #             model="Micro-Manager System",
    #         )
    #     instrument = Instrument(
    #         id="Instrument:0",
    #         microscope=microscope,
    #     )
    #     ome.instruments.append(instrument)
    # ...
    return []


def _get_dimension_info(
    image_infos: tuple[ImageInfo, ...],
) -> tuple[float, str | None, int, int]:
    """Extract pixel size (µm), data type, width, and height from image_infos."""
    pixel_size_um = 1.0
    dtype: str | None = None
    width = height = 0
    if image_infos and (img_info := image_infos[0]):
        pixel_size_um = img_info.get("pixel_size_um", 1.0)
        dtype = img_info.get("dtype")
        width, height = img_info.get("width", 0), img_info.get("height", 0)
    return pixel_size_um, dtype, height, width


def _get_acquisition_date(summary_metadata: SummaryMetaV1) -> datetime | None:
    acquisition_date = None
    if (acq_time := summary_metadata.get("datetime")) is not None:
        try:
            # parse ISO format datetime string
            acquisition_date = datetime.fromisoformat(acq_time.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass
    return acquisition_date


def _parse_position_key(key: str) -> tuple[str, str]:
    """Parse a position key to extract position name and image ID.

    Parameters
    ----------
    key : str
        Position key in format "PosName_p" or "PosName_Grid####_p_g"

    Returns
    -------
    tuple[str, str]
        A tuple of (position_name, image_id)
    """
    if "_Grid" in key:
        # Key format: "PosName_Grid####_p_g"
        parts = key.split("_")
        # Find the Grid part
        grid_idx = next(i for i, part in enumerate(parts) if part.startswith("Grid"))
        p_name = "_".join(parts[:grid_idx])
        grid_name = parts[grid_idx]
        position_name = f"{p_name}_{grid_name}"
        # Use combined p and g indices as the image ID
        p_index = parts[-2]
        g_index = parts[-1]
        image_id = f"{p_index}_{g_index}"
    else:
        # No grid, simple case: "PosName_p"
        p_name, p_index = key.rsplit("_", 1)
        position_name = p_name
        image_id = p_index

    return position_name, image_id


def _group_frames_by_position(
    frame_metadata_list: list[FrameMetaV1],
) -> dict[str, list[FrameMetaV1]]:
    """Reorganize frame metadata by stage position index in a dictionary.

    Handles the 'g' axis (grid) by converting it to separate positions,
    since OME doesn't support the 'g' axis. Each grid position becomes
    a separate OME Image with names like "Pos0000_Grid0000".
    """
    frames_by_position: dict[str, list[FrameMetaV1]] = {}
    for frame_meta in frame_metadata_list:
        mda_event = _get_mda_event(frame_meta)
        if mda_event is None:
            continue

        p_index = mda_event.index.get("p", 0) or 0
        g_index = mda_event.index.get("g", None)

        # get position name from event or generate default
        if hasattr(mda_event, "pos_name") and mda_event.pos_name:
            p_name = mda_event.pos_name
        else:
            p_name = f"Pos{p_index:04d}"

        # if grid index exists, include it in the position identifier
        if g_index is not None:
            key = f"{p_name}_Grid{g_index:04d}_{p_index}_{g_index}"
        else:
            key = f"{p_name}_{p_index}"

        if key not in frames_by_position:
            frames_by_position[key] = []

        frames_by_position[key].append(frame_meta)
    return frames_by_position


def _get_mda_event(frame_meta: FrameMetaV1) -> useq.MDAEvent | None:
    """Rdetrieve the useq.MDAEvent from frame metadata."""
    mda_event = frame_meta.get(MDA_EVENT)
    if mda_event is None:
        return None
    if not isinstance(mda_event, useq.MDAEvent):
        mda_event = useq.MDAEvent(**mda_event)
    return mda_event


def _get_pixels_info(
    pos_metadata: list[FrameMetaV1],
) -> tuple[tuple[int, int, int], list[Channel]]:
    """Get the position information from position metadata.

    Returns
    -------
        A tuple containing the maximum (t, z, c) indices, and a list of channels.
    """
    max_t, max_z, max_c = 0, 0, 0
    channels: dict[int, Channel] = {}  # Use int keys for better performance

    for frame_meta in pos_metadata:
        mda_event = _get_mda_event(frame_meta)
        if mda_event is None:
            continue

        # get indices with single dictionary lookups
        t_idx = mda_event.index.get("t", 0)
        z_idx = mda_event.index.get("z", 0)
        c_idx = mda_event.index.get("c", 0)

        max_t = max(max_t, t_idx)
        max_z = max(max_z, z_idx)
        max_c = max(max_c, c_idx)

        # create channel if not exists
        if c_idx not in channels and (ch := mda_event.channel) is not None:
            channels[c_idx] = Channel(
                id=f"Channel:{c_idx}",
                name=ch.config,
                samples_per_pixel=1,
            )

    # convert to sorted list by channel index
    sorted_channels = [channels[i] for i in sorted(channels.keys())]
    return (max_t + 1, max_z + 1, max_c + 1), sorted_channels


def _get_pixels_info_from_sequence(
    sequence: useq.MDASequence | dict,
) -> tuple[tuple[int, int, int], list[Channel]]:
    """Get the position information from a useq.MDASequence."""
    if isinstance(sequence, dict):
        sequence = useq.MDASequence(**sequence)
    max_t = sequence.sizes.get("t", 1)
    max_z = sequence.sizes.get("z", 1)
    channels = []
    for idx, ch in enumerate(sequence.channels):
        channels.append(
            Channel(
                id=f"Channel:{idx}",
                name=ch.config,
                samples_per_pixel=1,
            )
        )
    return (max_t, max_z, len(channels)), channels


def _get_planes(position_frames: list[FrameMetaV1]) -> list[Plane]:
    """Create Plane objects for a list of frame metadata at a specific position."""
    planes = []
    for frame_meta in position_frames:
        mda_event = _get_mda_event(frame_meta)
        if mda_event is None:
            continue

        # get indices
        event_index = mda_event.index
        z_idx = event_index.get("z", 0)
        c_idx = event_index.get("c", 0)
        t_idx = event_index.get("t", 0)

        # get time delta
        runner_time_ms = frame_meta.get("runner_time_ms", 0.0)
        delta_t = runner_time_ms / 1000.0 if runner_time_ms > 0 else None

        # get exposure time
        exposure_ms = frame_meta.get("exposure_ms", 0.0)

        plane = Plane(
            the_z=z_idx,
            the_c=c_idx,
            the_t=t_idx,
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


def _get_dimension_order_from_sequence(sequence: useq.MDASequence | dict) -> str:
    """
    Get axis order (fastest -> slowest) from a useq.MDASequence.

    Returns
    -------
    A string representing the dimension order compatible with OME standards
    (e.g., "XYCZT").
    """
    if isinstance(sequence, dict):
        sequence = useq.MDASequence(**sequence)
    ordered_axes = [ax for ax in sequence.axis_order if ax not in {"p", "g"}]
    dimension_order = "XY" + "".join(ordered_axes[::1]).upper()
    # if there are axis missing, add them
    if len(dimension_order) != 5:
        missing = [a for a in "XYCZT" if a not in dimension_order]
        dimension_order += "".join(missing)
    return dimension_order


def _get_dimension_order_from_frames(frames: Iterable[FrameMetaV1]) -> str:
    """
    Get axis order (fastest -> slowest) from a sequence of frame metadata dicts.

    Returns
    -------
    A string representing the dimension order compatible with OME standards
    (e.g., "XYCZT").
    """
    # extract index dicts (list of dicts mapping axis->int)
    idx_list: list[dict[str, int]] = []
    for f in frames:
        if (ev := _get_mda_event(f)) is None:
            continue
        idx_list.append({k: int(v) for k, v in ev.index.items() if k not in {"p"}})

    if not idx_list:
        return ""

    # Collect all axes seen
    axes = sorted({k for d in idx_list for k in d.keys()})

    # Compute unique counts and change counts
    uniques: dict[str, set] = {a: set() for a in axes}
    changes: dict[str, int] = dict.fromkeys(axes, 0)

    for i, d in enumerate(idx_list):
        for a in axes:
            val = d.get(a, 0)
            uniques[a].add(val)
            if i > 0:
                prev = idx_list[i - 1].get(a, 0)
                if val != prev:
                    changes[a] += 1

    sizes = {a: len(uniques[a]) for a in axes}
    # normalize by number of transitions to get frequency (optional)
    total_transitions = max(len(idx_list) - 1, 1)
    freqs = {a: changes[a] / total_transitions for a in axes}

    # Sort axes: highest change frequency first (fastest-varying).
    # Tie-breaker: larger unique count first, then axis name
    ordered_axes = sorted(
        axes,
        key=lambda a: (-freqs[a], -sizes[a], a),
    )
    # remove "g" if present since standard OME does not support it.
    # TODO: look for a way to handle it
    ordered_axes = [a for a in ordered_axes if a != "g"]

    dimension_order = "XY" + "".join(ordered_axes).upper()

    # if there are axis missing, add them
    if len(dimension_order) != 5:
        missing = [a for a in "XYCZT" if a not in dimension_order]
        dimension_order += "".join(missing)

    return dimension_order
