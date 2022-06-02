from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence, Union

import numpy as np
from useq import MDAEvent, MDASequence

from ._engine import PMDAEngine

try:
    import tifffile
except ImportError:
    tifffile = None

if TYPE_CHECKING:
    from ..core import CMMCorePlus


class MDAWriterBase:
    def __init__(self, core: CMMCorePlus = None) -> None:
        from ..core import CMMCorePlus

        self._core = core or CMMCorePlus.instance()
        self._on_mda_engine_registered(self._core.mda, None)
        self._core.events.mdaEngineRegistered.connect(self._on_mda_engine_registered)
        # TODO add paused and finished events

    def onMDAStarted(self, sequence: MDASequence):
        ...

    def onMDAFrame(self, img: np.ndarray, event: MDAEvent):
        ...  # pragma: no cover

    def onMDAFinished(self, sequence: MDASequence):
        ...

    def _on_mda_engine_registered(
        self, newEngine: PMDAEngine, oldEngine: Optional[PMDAEngine] = None
    ):
        if oldEngine:
            self._disconnect(oldEngine)
        newEngine.events.sequenceStarted.connect(self.onMDAStarted)
        newEngine.events.frameReady.connect(self.onMDAFrame)
        newEngine.events.sequenceFinished.connect(self.onMDAFinished)

    def _disconnect(self, engine: PMDAEngine):
        engine.events.sequenceStarted.disconnect(self.onMDAStarted)
        engine.events.frameReady.disconnect(self.onMDAFrame)
        engine.events.sequenceFinished.disconnect(self.onMDAFinished)

    def disconnect(self):
        "Disconnect this writer from processing any more events"
        self._disconnect(self._core.mda)

    @staticmethod
    def get_unique_folder(
        folder_base_name: Union[str, Path],
        suffix: Union[str, Path] = None,
        create: bool = False,
    ) -> Path:
        """
        Get a unique foldername of the form '{folder_base_name}_{i}

        Parameters
        ----------
        folder_base_name : str or Path
            The folder name in which to put data
        suffix : str or Path
            If given, to be used as the path suffix. e.g. `.zarr`
        create : bool, default False
            Whether to create the folder.
        '"""
        folder = Path(folder_base_name).resolve()
        stem = str(folder.stem)

        def new_path(i):
            path = folder.parent / (stem + f"_{i}")
            if suffix:
                return path.with_suffix(suffix)
            return path

        i = 1
        path = new_path(i)
        while path.exists():
            i += 1
            path = new_path(i)
        if create:
            path.mkdir(parents=True)
        return path

    @staticmethod
    def sequence_axis_order(seq: MDASequence) -> tuple[str]:
        """Get the axis order using only axes that are present in events."""
        # hacky way to drop unncessary parts of the axis order
        # e.g. drop the `p` in `tpcz` if there is only one position
        # TODO: add a better implementation upstream in useq
        event = next(seq.iter_events())
        event_axes = list(event.index.keys())
        return tuple(a for a in seq.axis_order if a in event_axes)

    @staticmethod
    def event_to_index(axis_order: Sequence[str], event: MDAEvent) -> tuple[int, ...]:
        return tuple(event.index[a] for a in axis_order)


class MDATiffWriter(MDAWriterBase):
    def __init__(
        self, data_folder_name: Union[str, Path], core: CMMCorePlus = None
    ) -> None:
        if tifffile is None:
            raise ValueError(
                "This writer requires tifffile to be installed. "
                "Try: `pip install tifffile`"
            )
        super().__init__(core)
        self._data_folder_name = data_folder_name

    def onMDAStarted(self, sequence: MDASequence) -> None:
        self._path = self.get_unique_folder(self._data_folder_name, create=True)
        self._axis_order = self.sequence_axis_order(sequence)
        with open(self._path / "useq-sequence.json", "w") as f:
            f.write(sequence.json())

    def onMDAFrame(self, img: np.ndarray, event: MDASequence) -> None:
        index = self.event_to_index(self._axis_order, event)
        name = (
            "_".join(
                [
                    self._axis_order[i] + f"{index[i]}".zfill(3)
                    for i in range(len(index))
                ]
            )
            + ".tiff"
        )
        tifffile.imwrite(self._path / name, img)
