from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Callable

from ._device import Device

if TYPE_CHECKING:
    from collections.abc import Mapping

    import numpy as np
    from numpy.typing import DTypeLike

# array should be (M, N) or (M, N, 3)
# Core does *not* copy the buffer.


class Camera(Device):
    @abstractmethod
    def shape(self) -> tuple[int, int]:
        """Return the shape of the image buffer."""

    @abstractmethod
    def dtype(self) -> DTypeLike:
        """Return the data type of the image buffer."""

    def start_sequence(
        self,
        n: int,
        get_buffer: Callable[[], np.ndarray],
        notify: Callable[[Mapping], None],
    ) -> None:
        """Start a sequence acquisition.

        This method should NOT block, and SHOULD return immediately.
        You should start a background thread to acquire images.

        Parameters
        ----------
        n : int
            The number of images to acquire.
        get_buffer : Callable[[], np.ndarray]
            A callable that returns a buffer to be filled with the image data.
            The buffer will be a numpy array with the shape and dtype
            returned by `shape()` and `dtype()`.
            The point here is that the core creates the buffer, and the device adapter
            should just mutate it in place with the image data.
        notify : Callable[[Mapping], None]
            A callable that should be called with a mapping of metadata
            after the buffer has been filled with image data.
        """
        for _ in range(n):
            image = get_buffer()

            # you MAY call get buffer multiple times before calling notify
            # ... however, you must call notify the same number of times that
            # you call get_buffer.  And semantically, each call to notify means
            # that the buffer corresponding to the first unresolved call to get_buffer
            # is now ready to be used.
            # image2 = get_buffer()

            # get the image from the camera, and fill the buffer in place
            image[:] = ...
            # image2[:] = ...

            # notify the core that the buffer is ready
            # the number of times you call notify must match the number of
            # times you call get_buffer ... and order must be the same
            # Calling `notify` more times than `get_buffer` results in a RuntimeError.
            notify({})
            # notify({})
