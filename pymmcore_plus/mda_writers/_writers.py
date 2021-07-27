from pathlib import Path
from typing import Tuple

import numpy as np
from typing_extensions import Protocol  # typing extensions for 3.7 support
from useq import MDAEvent, MDASequence

try:
    import tifffile
except ImportError:
    tifffile = None


def get_axis_order(seq: MDASequence) -> Tuple[str]:
    """Get the axis order using only axes that are present in events."""
    event = next(seq.iter_events())
    event_axes = list(event.index.keys())
    return tuple(a for a in seq.axis_order if a in event_axes)


class MDAWriter(Protocol):
    def initialize(self, shape, axis_order, seq: MDASequence, dtype: np.dtype) -> None:
        ...

    def addFrame(self, image, index, event: MDAEvent) -> None:
        ...

    def finalize(self) -> None:
        ...

    @staticmethod
    def get_unique_folder(folder_base_name: str) -> Path:
        base_path = Path.cwd()
        path: Path = base_path / folder_base_name
        i = 1
        while path.exists():
            path = base_path / (folder_base_name + f"_{i}")
            i += 1
        return path


class MDA_multifile_tiff_writer(MDAWriter):
    def __init__(self, data_folder_name: str) -> None:
        if tifffile is None:
            raise ValueError(
                "This writer requires tifffile to be installed. `pip install tifffile`"
            )
        self._path = self.get_unique_folder(data_folder_name)
        self._path.mkdir(parents=True)

    def initialize(self, shape, axis_order, seq: MDASequence, dtype: np.dtype) -> None:
        self._axis_order = axis_order

    def addFrame(self, img: np.ndarray, index, event: MDASequence) -> None:
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
