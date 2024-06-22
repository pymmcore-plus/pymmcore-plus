from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.metadata import (
    FrameMetaV1,
    SummaryMetaV1,
    frame_metadata,
    serialize,
    summary_metadata,
)


def test_create_schema() -> None:
    serialize.msgspec_to_schema(SummaryMetaV1)
    serialize.msgspec_to_schema(FrameMetaV1)


def test_from_core(core: CMMCorePlus) -> None:
    summary = summary_metadata(core, {})
    assert isinstance(summary, dict)
    frame = frame_metadata(core, {})
    assert isinstance(frame, dict)
