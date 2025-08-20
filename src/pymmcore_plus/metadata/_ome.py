from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from ome_types import model as ome_model
from ome_types import to_xml
from ome_types.model import (
    OME,
    Channel,
    Image,
    Instrument,
    Microscope,
    Pixels,
    Pixels_DimensionOrder,
    PixelType,
    Plane,
    StageLabel,
    UnitsLength,
    UnitsTime,
)

from .serialize import to_builtins

if TYPE_CHECKING:
    import useq

    from .schema import FrameMetaV1, SummaryMetaV1


def summary_metadata_to_ome(
    metadata: SummaryMetaV1,
    *,
    target_format: Literal["model", "xml", "json"] = "model",
) -> OME | str:
    """Convert pymmcore-plus metadata to an ome-types OME model or serialized string.

    Parameters
    ----------
    metadata : FrameMetaV1 | SummaryMetaV1
        The pymmcore-plus metadata to convert. Can be either summary metadata
        (from sequenceStarted) or frame metadata (from frameReady).
    target_format : Literal["model", "xml", "json"]
        The target format. "model" returns the OME model object,
        "xml" returns OME-XML as a string, "json" returns OME-JSON as a string.

    Returns
    -------
    OME | str
        The converted OME metadata in the requested format.
    """
    ome = _summary_to_ome(to_builtins(metadata))

    if target_format == "model":
        return ome
    elif target_format == "xml":
        return to_xml(ome)
    elif target_format == "json":
        return ome.model_dump_json()
    else:
        raise ValueError(f"Unsupported target_format: {target_format}")


def _summary_to_ome(summary_meta: dict) -> OME:
    """Convert summary metadata to OME model."""
    ome = OME(uuid=f"urn:uuid:{uuid.uuid4()}")

    # Extract image information
    image_infos = summary_meta.get("image_infos", [])
    if not image_infos:
        # Create a default image info if none present
        image_infos = [{"roi": (0, 0, 512, 512), "pixel_type": "uint16"}]

    # Get pixel size from image_infos, pixel_size_configs, or use default
    pixel_size_um = 1.0

    # First try to get pixel size from image_infos (most direct)
    if image_infos and image_infos[0].get("pixel_size_um"):
        pixel_size_um = image_infos[0]["pixel_size_um"]
    else:
        # Fallback to pixel_size_configs
        pixel_size_configs = summary_meta.get("pixel_size_configs", [])
        if pixel_size_configs and pixel_size_configs[0].get("pixel_size_um"):
            pixel_size_um = pixel_size_configs[0]["pixel_size_um"]

    # Extract channel information from mda_sequence (actual channels used)
    channels = []
    mda_sequence = summary_meta.get("mda_sequence")

    if mda_sequence and "channels" in mda_sequence:
        seq_channels = mda_sequence["channels"]
        # Use actual channels from the MDA sequence
        for i, seq_channel in enumerate(seq_channels):
            channel_name = (
                seq_channel.get("config", f"Channel_{i}")
                if isinstance(seq_channel, dict)
                else f"Channel_{i}"
            )
            channel = Channel(
                id=f"Channel:{i}",
                name=channel_name,
                samples_per_pixel=1,
            )
            channels.append(channel)

    # If no channels found, create a default one
    # if not channels:
    #     channels = [Channel(id="Channel:0", name="Channel_0", samples_per_pixel=1)]

    # Create instrument information
    instrument = None
    devices = summary_meta.get("devices", [])
    microscope_device = None
    camera_device = None

    for device in devices:
        if device.get("type") == "Core":
            microscope_device = device
        elif device.get("type") == "Camera":
            camera_device = device

    if microscope_device or camera_device:
        microscope = None
        if microscope_device:
            microscope = Microscope(
                manufacturer=microscope_device.get("description", "Unknown"),
                model="Micro-Manager System",
            )

        instrument = Instrument(
            id="Instrument:0",
            microscope=microscope,
        )
        ome.instruments.append(instrument)

    # Create image for the current system state
    for i, img_info in enumerate(image_infos):
        roi = img_info.get("roi", (0, 0, 512, 512))
        x, y, width, height = roi

        # Map pixel type string to OME enum
        pixel_type_str = img_info.get("pixel_type", "uint16")
        pixel_type = getattr(PixelType, pixel_type_str.upper(), PixelType.UINT16)

        pixels = Pixels(
            id=f"Pixels:{i}",
            dimension_order=Pixels_DimensionOrder.XYCZT,
            size_x=width,
            size_y=height,
            size_z=1,
            size_c=len(channels),
            size_t=1,
            type=pixel_type,
            physical_size_x=pixel_size_um,
            physical_size_x_unit=UnitsLength.MICROMETER,
            physical_size_y=pixel_size_um,
            physical_size_y_unit=UnitsLength.MICROMETER,
            channels=channels,
        )

        image = Image(
            id=f"Image:{i}",
            name=f"Image_{i}",
            pixels=pixels,
        )

        # Add acquisition date if available
        if "datetime" in summary_meta:
            try:
                # Parse ISO format datetime string
                acq_date = datetime.fromisoformat(
                    summary_meta["datetime"].replace("Z", "+00:00")
                )
                image.acquisition_date = acq_date
            except (ValueError, AttributeError):
                pass

        # Link to instrument if available
        if instrument:
            image.instrument_ref = ome_model.InstrumentRef(id=instrument.id)

        ome.images.append(image)

    return ome


def _create_plane_from_frame(
    frame_meta: dict, the_z: int = 0, the_c: int = 0, the_t: int = 0
) -> Plane | None:
    """Create a Plane object from frame metadata.

    Parameters
    ----------
    frame_meta : dict
        Frame metadata dictionary
    the_z, the_c, the_t : int
        Logical coordinates for the plane (defaults to 0)

    Returns
    -------
    Plane | None
        Plane object with timing and position information, or None if no plane data
    """
    runner_time_ms = frame_meta.get("runner_time_ms", 0.0)
    exposure_ms = frame_meta.get("exposure_ms")

    # Only create plane if we have timing or position info
    if not (runner_time_ms > 0 or exposure_ms or frame_meta.get("position")):
        return None

    plane = Plane(
        the_z=the_z,
        the_c=the_c,
        the_t=the_t,
    )

    # Add timing information
    if runner_time_ms > 0:
        plane.delta_t = runner_time_ms / 1000.0  # Convert to seconds
        plane.delta_t_unit = UnitsTime.SECOND

    if exposure_ms:
        plane.exposure_time = exposure_ms / 1000.0  # Convert to seconds
        plane.exposure_time_unit = UnitsTime.SECOND

    # Add position if available (frame metadata format)
    position = frame_meta.get("position")
    if position:
        stage_positions = position.get("stage_positions", [])
        for stage_pos in stage_positions:
            if stage_pos.get("device") == "XYStage":
                plane.position_x = stage_pos.get("position", 0.0)
                plane.position_x_unit = UnitsLength.MICROMETER
            elif stage_pos.get("device") == "ZStage":
                plane.position_z = stage_pos.get("position", 0.0)
                plane.position_z_unit = UnitsLength.MICROMETER

    return plane


def create_ome_metadata(
    mda_sequence: useq.MDASequence,
    summary_metadata: SummaryMetaV1,
    frame_metadata_list: list[FrameMetaV1],
    *,
    target_format: Literal["model", "xml", "json"] = "model",
) -> OME | str | None:
    """Create enhanced OME metadata from summary and frame metadata collections.

    This function organizes frame metadata by position and creates separate
    Image elements for each stage position with proper plane information.

    Parameters
    ----------
    mda_sequence : useq.MDASequence
        The MDA sequence used for the acquisition
    summary_metadata : SummaryMetaV1
        The summary metadata from sequence setup
    frame_metadata_list : list[FrameMetaV1]
        List of frame metadata collected during acquisition
    target_format : Literal["model", "xml", "json"]
        The target format for the output, ome-types object ("model"),
        OME-XML string ("xml"), or OME-JSON string ("json").
    """
    # Start with base OME from summary metadata
    base_ome = summary_metadata_to_ome(summary_metadata, target_format="model")

    # Check if we have an OME model object
    if base_ome is None or isinstance(base_ome, str):
        return None

    # If no frame metadata collected, return base OME
    if not frame_metadata_list:
        if target_format == "model":
            return base_ome
        elif target_format == "xml":
            return to_xml(base_ome)
        elif target_format == "json":
            return base_ome.model_dump_json()

    # Organize frames by position
    frames_by_position: dict[int, list[FrameMetaV1]] = {}
    stage_positions = mda_sequence.stage_positions

    for frame_meta in frame_metadata_list:
        mda_event = frame_meta.get("mda_event")
        if mda_event:
            p_index = mda_event.index.get("p", 0) or 0
            if p_index not in frames_by_position:
                frames_by_position[p_index] = []
            frames_by_position[p_index].append(frame_meta)

    # Calculate dimensions per position
    if not frames_by_position:
        if target_format == "model":
            return base_ome
        elif target_format == "xml":
            return to_xml(base_ome)
        elif target_format == "json":
            return base_ome.model_dump_json()

    # Analyze dimensions from first position
    first_pos_frames = next(iter(frames_by_position.values()))
    max_z = max_c = max_t = 0

    for frame_meta in first_pos_frames:
        mda_event = frame_meta.get("mda_event")
        if mda_event:
            max_z = max(max_z, (mda_event.index.get("z", 0) or 0) + 1)
            max_c = max(max_c, (mda_event.index.get("c", 0) or 0) + 1)
            max_t = max(max_t, (mda_event.index.get("t", 0) or 0) + 1)

    # Create images for each position
    images = []
    for p_index in sorted(frames_by_position.keys()):
        position_frames = frames_by_position[p_index]

        # Create image for this position
        image_id = f"Image:{p_index}"
        image_name = f"Position_{p_index}"

        # Create pixels with proper dimensions
        pixels_template = base_ome.images[0].pixels if base_ome.images else None
        if not pixels_template:
            continue

        pixels = Pixels(
            id=f"Pixels:{p_index}",
            dimension_order=pixels_template.dimension_order,
            type=pixels_template.type,
            size_x=pixels_template.size_x,
            size_y=pixels_template.size_y,
            size_z=max_z,
            size_c=max_c,
            size_t=max_t,
            physical_size_x=pixels_template.physical_size_x,
            physical_size_x_unit=pixels_template.physical_size_x_unit,
            physical_size_y=pixels_template.physical_size_y,
            physical_size_y_unit=pixels_template.physical_size_y_unit,
        )

        # Copy channels from base OME
        if pixels_template.channels:
            pixels.channels = []
            for i, base_channel in enumerate(pixels_template.channels):
                channel = base_channel.model_copy()
                channel.id = f"Channel:{p_index}:{i}"
                pixels.channels.append(channel)

        # Create planes for this position using _create_plane_from_frame
        planes = []
        for frame_meta in position_frames:
            mda_event = frame_meta.get("mda_event")
            if mda_event and hasattr(mda_event, "index"):
                the_z = mda_event.index.get("z", 0) or 0
                the_c = mda_event.index.get("c", 0) or 0
                the_t = mda_event.index.get("t", 0) or 0

                # Use the helper function to create plane with full metadata
                plane = _create_plane_from_frame(
                    to_builtins(frame_meta), the_z=the_z, the_c=the_c, the_t=the_t
                )

                if plane:
                    # Add position coordinates from MDA event if available
                    if hasattr(mda_event, "x_pos") and mda_event.x_pos is not None:
                        plane.position_x = mda_event.x_pos
                        plane.position_x_unit = UnitsLength.MICROMETER
                    if hasattr(mda_event, "y_pos") and mda_event.y_pos is not None:
                        plane.position_y = mda_event.y_pos
                        plane.position_y_unit = UnitsLength.MICROMETER
                    if hasattr(mda_event, "z_pos") and mda_event.z_pos is not None:
                        plane.position_z = mda_event.z_pos
                        plane.position_z_unit = UnitsLength.MICROMETER

                    planes.append(plane)

        pixels.planes = planes

        # Create the image
        image_kwargs = {
            "id": image_id,
            "name": image_name,
            "pixels": pixels,
        }

        # Add acquisition date from base OME
        if base_ome.images and base_ome.images[0].acquisition_date:
            image_kwargs["acquisition_date"] = base_ome.images[0].acquisition_date

        # Get position coordinates
        stage_pos = None
        if p_index < len(stage_positions):
            stage_pos = stage_positions[p_index]

        # Add stage label if position coordinates available
        if stage_pos:
            x_pos = stage_pos.x or 0.0
            y_pos = stage_pos.y or 0.0
            z_pos = stage_pos.z or 0.0
            stage_label = StageLabel(x=x_pos, y=y_pos, z=z_pos, name=f"P{p_index}")
            image_kwargs["stage_label"] = stage_label

        image = Image(**image_kwargs)
        images.append(image)

    # Update the base OME with new images
    if hasattr(base_ome, "images"):
        base_ome.images = images

    # Return in requested format
    if target_format == "model":
        return base_ome
    elif target_format == "xml":
        return to_xml(base_ome)
    elif target_format == "json":
        return base_ome.model_dump_json()
    else:
        raise ValueError(f"Unsupported target_format: {target_format}")
