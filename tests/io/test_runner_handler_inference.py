from __future__ import annotations

from typing import Any

import pytest
from pymmcore_plus.mda import MDARunner
from pymmcore_plus.mda.handlers import (
    ImageSequenceWriter,
    OMETiffWriter,
    OMEZarrWriter,
    TensorStoreHandler,
)

NEUROGLANCER = "neuroglancer_precomputed"

inputs = [
    ("./test.tensorstore.zarr", TensorStoreHandler, "zarr"),
    ("./test.tensorstore.zarr3", TensorStoreHandler, "zarr3"),
    ("./test.tensorstore.n5", TensorStoreHandler, "n5"),
    (f"./test.tensorstore.{NEUROGLANCER}", TensorStoreHandler, NEUROGLANCER),
    ("./test.zarr", OMEZarrWriter, ""),
    ("./test.tif", OMETiffWriter, ""),
    ("./test.tiff", OMETiffWriter, ""),
    ("./test", ImageSequenceWriter, ""),
]


@pytest.mark.parametrize("input", inputs)
def test_runner_handler_inference(input: tuple[str, Any]):
    runner = MDARunner()
    path, expected_handler, driver = input
    handler = runner._handler_for_path(path)
    assert isinstance(handler, expected_handler)
    if isinstance(handler, TensorStoreHandler):
        assert handler.ts_driver == driver
