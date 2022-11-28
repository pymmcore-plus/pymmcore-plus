from pymmcore_plus import CMMCorePlus
from pymmcore_plus._logger import logger
from useq import MDAEvent, MDASequence


def _is_sequenceable(
    core: CMMCorePlus, e1: MDAEvent, e2: MDAEvent, cur_length: int
) -> bool:
    # maybe check if last event

    # channel
    if e1.channel and e2.channel and (e1.channel != e2.channel):
        cfg = core.getConfigData(e1.channel.group, e1.channel.config)
        for devLabeL, propLabel, _ in cfg:
            # note: we don't need _ here, so can perhaps speed up with native=True
            if core.isPropertySequenceable(devLabeL, propLabel):
                return False
            if cur_length >= core.getPropertySequenceMaxLength(devLabeL, propLabel):
                return False

    # TODO: check e1.properties and e2.properties

    # Z
    if e1.z_pos and e2.z_pos and (e1.z_pos != e2.z_pos):
        focus_dev = core.getFocusDevice()
        if not core.isStageSequenceable(focus_dev):
            return False
        if cur_length >= core.getStageSequenceMaxLength(focus_dev):
            return False

    # XY
    if (e1.x_pos and e2.x_pos and (e1.x_pos != e2.x_pos)) or (
        e1.y_pos and e2.y_pos and (e1.y_pos != e2.y_pos)
    ):
        stage = core.getXYStageDevice()
        if not core.isXYStageSequenceable(stage):
            return False
        if cur_length >= core.getXYStageSequenceMaxLength(stage):
            return False

    # camera
    cam_dev = core.getCameraDevice()
    cam_can_seq = core.isExposureSequenceable(cam_dev)
    if e1.exposure and e2.exposure and (e1.exposure != e2.exposure) and not cam_can_seq:
        return False
    if cam_can_seq and cur_length >= core.getExposureSequenceMaxLength(cam_dev):
        return False

    # time
    # FIXME: use axis constants
    if e1.index["T"] != e2.index["T"] and e1.min_start_time != e2.min_start_time:
        return False

    return True


def _submit_event_iterator(core: CMMCorePlus, sequence: MDASequence):
    _burst: list[MDAEvent] = []

    for event in sequence:
        logger.debug(f"event: {event}")
        # run hooks: on_event(event) -> bool

        # processAcquisitionEvent
        if _burst:
            if _is_sequenceable(core, _burst[-1], event):
                ...
        else:
            _burst.append(event)
