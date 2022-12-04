import numpy as np
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
