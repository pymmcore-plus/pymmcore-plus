from collections.abc import Iterable
from typing import Any, cast
from unittest.mock import MagicMock

from pymmcore_plus.core._mmcore_plus import CMMCorePlus
from pymmcore_plus.mda._engine import MDAEngine
from pymmcore_plus.mda._runner import MDARunner


class MockSequenceableCore(MagicMock):
    """Sequenceable mock for testing."""

    def __init__(self, *args: Any, max_len: int = 100, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        from pymmcore_plus import CMMCorePlus

        if isinstance(kwargs.get("wraps", None), CMMCorePlus):
            self.isExposureSequenceable.return_value = True
            self.getExposureSequenceMaxLength.return_value = max_len

            self.isStageSequenceable.return_value = True
            self.getStageSequenceMaxLength.return_value = max_len

            self.isXYStageSequenceable.return_value = True
            self.getXYStageSequenceMaxLength.return_value = max_len

            self.getSLMSequenceMaxLength.return_value = max_len
            self.getPropertySequenceMaxLength.return_value = max_len

            self.isPropertySequenceable.side_effect = self._isPropertySequenceable

            self.loadExposureSequence.return_value = None
            self.loadStageSequence.return_value = None
            self.loadXYStageSequence.return_value = None
            self.loadSLMSequence.return_value = None

            self.loadPropertySequence.return_value = None

            self.startExposureSequence.return_value = None
            self.stopExposureSequence.return_value = None

            self.startStageSequence.return_value = None
            self.stopStageSequence.return_value = None

            self.startXYStageSequence.return_value = None
            self.stopXYStageSequence.return_value = None

            self.startPropertySequence.return_value = None
            self.stopPropertySequence.return_value = None

    def _isPropertySequenceable(self, dev: str, prop: str) -> bool:
        # subclass to implement more interesting behavior
        return True


def mock_sequenceable_core(
    roi: tuple[int, int, int, int] = (0, 0, 512, 512),
    image_bit_depth: int = 16,
    image_width: int = 512,
    image_height: int = 512,
    bytes_per_pixel: int = 2,
    number_of_camera_channels: int = 1,
    number_of_components: int = 1,
    xy_position: tuple[float, float] = (0.0, 0.0),
    pixel_size_um: float = 1.0,
    auto_shutter: bool = True,
    exposure_sequence_max_length: int = 0,
    # ((label, property), max_length)
    property_sequences_max_lengths: bool | Iterable[tuple[tuple[str, str], int]] = (),
) -> CMMCorePlus:
    real_core = CMMCorePlus()
    real_core.loadSystemConfiguration()
    mock_core = cast("CMMCorePlus", MagicMock(wraps=real_core))
    mock_core._mda_runner = mock_core.mda = MDARunner()
    mock_core.mda.set_engine(MDAEngine(mock_core))

    # return values
    # mock_core.getROI.return_value = roi
    # mock_core.getImageBitDepth.return_value = image_bit_depth
    # mock_core.getImageWidth.return_value = image_width
    # mock_core.getImageHeight.return_value = image_height
    # mock_core.getBytesPerPixel.return_value = bytes_per_pixel
    # mock_core.getNumberOfCameraChannels.return_value = number_of_camera_channels
    # mock_core.getNumberOfComponents.return_value = number_of_components
    # mock_core.getXYPosition.return_value = xy_position
    # mock_core.getXPosition.return_value = xy_position[0]
    # mock_core.getYPosition.return_value = xy_position[1]
    # mock_core.getPixelSizeUm.return_value = pixel_size_um
    # mock_core.getAutoShutter.return_value = auto_shutter

    mock_core.getExposureSequenceMaxLength.return_value = exposure_sequence_max_length
    mock_core.isExposureSequenceable.return_value = exposure_sequence_max_length > 0

    if isinstance(property_sequences_max_lengths, (bool, int)):
        max_len = (
            property_sequences_max_lengths
            if isinstance(property_sequences_max_lengths, int)
            else 1000
        )

        def _is_prop_seq(dev: str, prop: str) -> bool:
            return property_sequences_max_lengths

        def _prop_seq_len(dev: str, prop: str) -> int:
            return 0 if not property_sequences_max_lengths else max_len

    else:
        prop_max_lengths = dict(property_sequences_max_lengths)
        sequenceable_properties = {x for x, v in prop_max_lengths.items() if v > 0}

        def _is_prop_seq(dev: str, prop: str) -> bool:
            return (dev, prop) in sequenceable_properties

        def _prop_seq_len(dev: str, prop: str) -> int:
            return prop_max_lengths.get((dev, prop), 0)

    mock_core.isPropertySequenceable.side_effect = _is_prop_seq
    mock_core.getPropertySequenceMaxLength.side_effect = _prop_seq_len
    return mock_core
