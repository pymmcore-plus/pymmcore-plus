from typing import Any
from unittest.mock import MagicMock


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
