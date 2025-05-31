from __future__ import annotations

import threading
from abc import abstractmethod
from typing import TYPE_CHECKING, Callable

from ._device import Device

if TYPE_CHECKING:
    from collections.abc import Mapping

    import numpy as np
    from numpy.typing import DTypeLike


class Camera(Device):
    def __init__(self) -> None:
        super().__init__()
        self._acquisition_thread: None | threading.Thread = None
        self._stop_event = threading.Event()

    @abstractmethod
    def shape(self) -> tuple[int, int]:
        """Return the shape of the image buffer.

        This is used when querying Width, Height, *and* number of components.
        If the camera is grayscale, it should return (width, height).
        If the camera is color, it should return (width, height, n_channels).
        """

    @abstractmethod
    def dtype(self) -> DTypeLike:
        """Return the data type of the image buffer."""

    @abstractmethod
    def start_sequence(
        self,
        n: int,
        get_buffer: Callable[[], np.ndarray],
        notify: Callable[[Mapping], None],
    ) -> None:
        """Start a sequence acquisition.

        This method should be implemented by the camera device adapter. It needn't worry
        about threading or synchronization; it may block and the core will handle
        threading and synchronization, though you may reimplement
        `start_sequence_thread` if you'd like to handle threading yourself.

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
        # EXAMPLE USAGE:
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

            # TODO:
            # Open question: who is responsible for key pieces of metadata?
            # in CMMCore, each of the camera device adapters is responsible for
            # injecting to following bits of metadata:
            # - MM::g_Keyword_Metadata_CameraLabel
            # - MM::g_Keyword_Elapsed_Time_ms (GetCurrentMMTime - start_time)
            # - MM::g_Keyword_Metadata_ROI_X
            # - MM::g_Keyword_Metadata_ROI_Y
            # - MM::g_Keyword_Binning
            # --- while the CircularBuffer InsertMultiChannel is responsible for adding:
            # - MM::g_Keyword_Metadata_ImageNumber
            # - MM::g_Keyword_Elapsed_Time_ms
            # - MM::g_Keyword_Metadata_TimeInCore
            # - MM::g_Keyword_Metadata_Width
            # - MM::g_Keyword_Metadata_Height
            # - MM::g_Keyword_PixelType

            # for example:
            # {
            #     "Binning": "1",
            #     "Camera": "Camera",
            #     "ElapsedTime-ms": "30.50",
            #     "Height": "512",
            #     "ImageNumber": "2",
            #     "PixelType": "GRAY16",
            #     "ROI-X-start": "0",
            #     "ROI-Y-start": "0",
            #     "TimeReceivedByCore": "2025-05-31 09:26:07.964891",
            #     "Width": "512",
            # }

    def start_sequence_thread(
        self,
        n: int,
        get_buffer: Callable[[], np.ndarray],
        notify: Callable[[Mapping], None],
    ) -> None:
        """Acquire a sequence of n images in a background thread."""
        # Stop any existing acquisition
        self._stop_event.set()
        if self._acquisition_thread is not None:
            self._acquisition_thread.join()

        # Reset stop event for new acquisition
        self._stop_event.clear()

        # Start acquisition in background thread
        self._acquisition_thread = threading.Thread(
            target=self.start_sequence, args=(n, get_buffer, notify), daemon=True
        )
        self._acquisition_thread.start()

    def stop_sequence(self) -> None:
        """Stop the current sequence acquisition."""
        self._stop_event.set()
        if self._acquisition_thread is not None:
            self._acquisition_thread.join()
            self._acquisition_thread = None
