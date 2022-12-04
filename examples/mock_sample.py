from typing import Iterator, Tuple

import numpy as np
from pymmcore_plus import CMMCorePlus, mock_sample

core = CMMCorePlus()
core.loadSystemConfiguration()

# decorate a function that yields numpy arrays with @mock_sample
@mock_sample(mmcore=core, loop=True)
def noisy_sample(shape: Tuple[int, int] = (10, 10)) -> Iterator[np.ndarray]:
    yield np.random.random(shape)


print(core.snap().shape)

# use it as a context manager.
# each time `core.getImage()` is called, a new image is yielded from the generator
with noisy_sample():
    for _ in range(3):
        print(core.snap().shape)

print(core.snap().shape)
