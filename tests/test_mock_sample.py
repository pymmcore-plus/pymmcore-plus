import numpy as np
import pytest
from pymmcore_plus import CMMCorePlus, mock_sample


def test_mock_sample(core: CMMCorePlus) -> None:
    SHAPE = (10, 10)

    @mock_sample(mmcore=core, loop=True)
    def noisy_sample():
        yield np.random.random(SHAPE)

    assert core.snap().shape != SHAPE

    with noisy_sample():
        for _ in range(3):
            assert core.snap().shape == SHAPE

    assert core.snap().shape != SHAPE


def test_mock_sample_mocks_snap_image() -> None:
    """Here we create a core without loading any config.

    Normally, calling `core.snapImage()` would raise an error, but the mock
    sample decorator obviates the need for a camera to be loaded.
    """
    core = CMMCorePlus()

    @mock_sample(mmcore=core)
    def noisy_sample():
        yield None

    with pytest.raises(RuntimeError, match="Camera not loaded or initialized"):
        core.snap()

    with noisy_sample():
        # no exception is raised
        assert core.snap() is None
