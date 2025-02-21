from __future__ import annotations

from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from types import TracebackType
    from unittest.mock import _patch

    import numpy as np
    from pymmcore import CMMCore
    from typing_extensions import ParamSpec

    from pymmcore_plus.metadata.schema import SummaryMetaV1

    P = ParamSpec("P")


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


class CorePatcher(AbstractContextManager):
    """Context manager that patches the provided (or global) mmcore object.

    Subclass this and implement methods that appear in CMMCorePlus. When the context
    manager is entered, the core object will be patched with the methods from the
    subclass instead.
    """

    def __init__(self, mmcore: CMMCore | None = None) -> None:
        from pymmcore_plus import CMMCorePlus

        self.mmcore = mmcore or CMMCorePlus.instance()

        self._patchers: list[_patch] = []
        for attr in dir(self):
            if hasattr(self.mmcore, attr):
                patcher = patch.object(
                    self.mmcore, attr, getattr(self, attr), autospec=True
                )
                self._patchers.append(patcher)

    def start(self) -> None:
        """Start all patchers."""
        for patcher in self._patchers:
            patcher.start()

    def stop(self) -> None:
        """Stop all patchers."""
        for patcher in self._patchers:
            patcher.stop()

    def __enter__(self) -> None:
        """Start all patchers."""
        self.start()

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Stop all patchers."""
        self.stop()


class MockSample(CorePatcher):
    def __init__(self, mmcore: CMMCore | None = None) -> None:
        super().__init__(mmcore)
        self._snapped_state: SummaryMetaV1 | None = None

    def snapImage(self) -> None:
        self._snapped_state = self.mmcore.state()

    def getImage(
        self, numChannel: int | None = None, *, fix: bool = True
    ) -> np.ndarray: ...
