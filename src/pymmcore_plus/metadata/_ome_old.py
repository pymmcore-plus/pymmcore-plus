from __future__ import annotations

import json
import tempfile
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import useq
from ome_types.model import (
    OME,
    Channel,
    Image,
    Instrument,
    Pixels,
    Pixels_DimensionOrder,
    PixelType,
    Plane,
    UnitsLength,
    UnitsTime,
)

from pymmcore_plus.mda._runner import GeneratorMDASequence

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from .schema import FrameMetaV1, SummaryMetaV1

MDA_EVENT = "mda_event"


def create_ome_metadata(
    summary_metadata: SummaryMetaV1,
    frame_metadata_list: list[FrameMetaV1],
) -> OME:
    """Create enhanced OME metadata from summary and frame metadata collections.

    This function organizes frame metadata by position and creates separate
    Image elements for each stage position with proper plane information.

    Parameters
    ----------
    summary_metadata : SummaryMetaV1
        The summary metadata from sequence setup
    frame_metadata_list : list[FrameMetaV1]
        List of frame metadata collected during acquisition

    Returns
    -------
    OME
        The OME metadata as an `ome_types.OME` object.
    """
    # create OME model
    ome = OME(uuid=f"urn:uuid:{uuid.uuid4()}")

    ome.instruments = _add_ome_instrument_info(summary_metadata)

    # if no frame metadata has been collected, return the OME model as it is
    if not frame_metadata_list:
        return ome

    # extract image information
    image_infos = summary_metadata.get("image_infos")

    if image_infos is None:
        return ome

    # get pixel size from image_infos
    pixel_size_um = 1.0
    dtype: str | None = None
    width = height = 0
    if image_infos and (img_info := image_infos[0]):
        pixel_size_um = img_info.get("pixel_size_um", 1.0)
        dtype = img_info.get("dtype")
        width, height = img_info.get("width", 0), img_info.get("height", 0)

    if dtype is None:
        return ome

    acquisition_date = _get_acquisition_date(summary_metadata)

    sequence = _get_mda_sequence(summary_metadata, frame_metadata_list[0])

    positions_map = _group_frames_by_position(frame_metadata_list)

    for key in positions_map:
        p_name, p_index = key.split("_")
        position_frames = positions_map[key]

        if sequence is not None:
            dimension_order = _get_dimension_order_from_sequence(sequence)
        else:
            dimension_order = _get_dimension_order(position_frames)

        if not dimension_order:
            # Pixels object cannot be created without a valid dimension order
            continue

        if sequence is None or isinstance(sequence, GeneratorMDASequence):
            (max_t, max_z, max_c), channels = _get_pixels_info(position_frames)
            print(max_t, max_z, max_c, channels)

        else:
            (max_t, max_z, max_c), channels = _get_pixels_info_from_sequence(sequence)

        pixels = Pixels(
            id=f"Pixels:{p_index}",
            dimension_order=Pixels_DimensionOrder(dimension_order),
            size_x=width,
            size_y=height,
            size_z=max_z,
            size_c=max_c,
            size_t=max_t,
            type=PixelType(dtype),
            physical_size_x=pixel_size_um,
            physical_size_x_unit=UnitsLength.MICROMETER,
            physical_size_y=pixel_size_um,
            physical_size_y_unit=UnitsLength.MICROMETER,
            channels=channels,
        )

        planes = []
        for frame_meta in position_frames:
            mda_event = frame_meta.get(MDA_EVENT)

            if mda_event is None:
                continue

            # get time delta
            runner_time_ms = frame_meta.get("runner_time_ms", 0.0)
            delta_t = runner_time_ms / 1000.0 if runner_time_ms > 0 else None
            delta_t_unit = UnitsTime.SECOND

            # get exposure time
            exposure_ms = frame_meta.get("exposure_ms", 0.0)
            exposure_time_unit = UnitsTime.MILLISECOND

            plane = Plane(
                the_z=mda_event.index.get("z", 0),
                the_c=mda_event.index.get("c", 0),
                the_t=mda_event.index.get("t", 0),
                position_x=mda_event.x_pos,
                position_x_unit=UnitsLength.MICROMETER,
                position_y=mda_event.y_pos,
                position_y_unit=UnitsLength.MICROMETER,
                position_z=mda_event.z_pos,
                position_z_unit=UnitsLength.MICROMETER,
                delta_t=delta_t,
                delta_t_unit=delta_t_unit,
                exposure_time=exposure_ms,
                exposure_time_unit=exposure_time_unit,
            )

            planes.append(plane)

        pixels.planes = planes

        image = Image(
            acquisition_date=acquisition_date,
            id=f"Image:{p_index}",
            name=p_name,
            pixels=pixels,
        )

        ome.images.append(image)

    return ome


def _add_ome_instrument_info(summary_meta: SummaryMetaV1) -> list[Instrument]:
    """Add instrument information to the OME model based on summary metadata."""
    # TODO: use devices to get info about microscope
    # Create instrument information
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


def _get_acquisition_date(summary_metadata: SummaryMetaV1) -> datetime | None:
    acquisition_date = None
    if (acq_time := summary_metadata.get("datetime")) is not None:
        try:
            # parse ISO format datetime string
            acquisition_date = datetime.fromisoformat(acq_time.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass
    return acquisition_date


def _group_frames_by_position(
    frame_metadata_list: list[FrameMetaV1],
) -> dict[str, list[FrameMetaV1]]:
    """Reorganize frame metadata by stage position index in a dictionary."""
    frames_by_position: dict[str, list[FrameMetaV1]] = {}
    for frame_meta in frame_metadata_list:
        mda_event = frame_meta.get(MDA_EVENT)
        if mda_event:
            p_index = mda_event.index.get("p", 0) or 0
            p_name = mda_event.index.get("pos_name", f"Pos{p_index:04d}")
            key = f"{p_name}_{p_index}"
            if key not in frames_by_position:
                frames_by_position[key] = []
            frames_by_position[key].append(frame_meta)
    return frames_by_position


def _get_pixels_info_from_sequence(
    sequence: useq.MDASequence,
) -> tuple[tuple[int, int, int], list[Channel]]:
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


def _get_pixels_info(
    pos_metadata: list[FrameMetaV1],
) -> tuple[tuple[int, int, int], list[Channel]]:
    """Get the position information from position metadata.

    Returns
    -------
        A tuple containing the maximum (t, z, c) indices, and a list of channels.
    """
    max_t, max_z, max_c = 0, 0, 0
    channels: dict[str, Channel] = {}
    for frame_meta in pos_metadata:
        mda_event = frame_meta.get(MDA_EVENT)
        if mda_event:
            max_t = max(max_t, mda_event.index.get("t", 0))
            max_z = max(max_z, mda_event.index.get("z", 0))
            max_c = max(max_c, mda_event.index.get("c", 0))
            if (ch := mda_event.channel) is not None:
                if (
                    ch_name := f"{ch.config}_{mda_event.index.get('c', 0)}"
                ) not in channels:
                    channels[ch_name] = Channel(
                        id=f"Channel:{mda_event.index.get('c', 0)}",
                        name=ch.config,
                        samples_per_pixel=1,
                    )
    return (max_t + 1, max_z + 1, max_c + 1), list(channels.values())


def _get_dimension_order_from_sequence(sequence: useq.MDASequence) -> str:
    """
    Get axis order (fastest -> slowest) from a useq.MDASequence.

    Returns
    -------
    A string representing the dimension order compatible with OME standards
    (e.g., "XYCZT").
    """
    ordered_axes = [ax for ax in sequence.axis_order if ax not in {"p", "g"}]
    dimension_order = "XY" + "".join(ordered_axes[::1]).upper()
    # if there are axis missing, add them
    if len(dimension_order) != 5:
        missing = [a for a in "XYCZT" if a not in dimension_order]
        dimension_order += "".join(missing)
    return dimension_order


def _get_dimension_order(frames: Iterable[FrameMetaV1]) -> str:
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
        if (ev := f.get(MDA_EVENT)) is None:
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


def _get_mda_sequence(
    summary_metadata: SummaryMetaV1, single_frame_metadata: FrameMetaV1
) -> useq.MDASequence | None:
    """Get the MDA sequence from summary metadata or frame metadata."""
    # get the mda_sequence from summary metadata
    seq = summary_metadata.get("mda_sequence")
    if seq:
        return seq
    # if is not there try form single_frame_metadata useq.MDAEvent
    ev = single_frame_metadata.get(MDA_EVENT, useq.MDAEvent())
    return ev.sequence
