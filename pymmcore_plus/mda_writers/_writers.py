from pathlib import Path
from typing import Union

import numpy as np
from typing_extensions import Protocol  # typing extensions for 3.7 support
from useq import MDAEvent, MDASequence

try:
    import tifffile
except ImportError:
    tifffile = None


class MDAWriter(Protocol):
    def initialize(self, shape, axis_order, seq: MDASequence, dtype: np.dtype) -> None:
        ...

    def addFrame(self, image, index, event: MDAEvent) -> None:
        ...

    def finalize(self) -> None:
        ...

    @staticmethod
    def get_unique_folder(folder_base_name: Union[str, Path]) -> Path:
        base_path = Path.cwd()
        folder = str(folder_base_name)
        path: Path = base_path / folder
        i = 1
        while path.exists():
            path = base_path / (folder + f"_{i}")
            i += 1
        return path


class MDA_multifile_tiff_writer(MDAWriter):
    def __init__(self, data_folder_name: Union[str, Path]) -> None:
        if tifffile is None:
            raise ValueError(
                "This writer requires tifffile to be installed. `pip install tifffile`"
            )
        self._data_folder_name = data_folder_name

    def initialize(self, shape, axis_order, seq: MDASequence, dtype: np.dtype) -> None:
        self._path = self.get_unique_folder(self._data_folder_name)
        self._path.mkdir(parents=True)
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
