import threading
import time
from collections.abc import Mapping
from typing import Callable, Union

import numpy as np
import pytest
from numpy.typing import DTypeLike

from pymmcore_plus.experimental.unicore import Camera
from pymmcore_plus.experimental.unicore.core._unicore import UniMMCore

DEV = "Camera"

np.random.seed(42)
FRAME_SHAPE = (512, 512)
DTYPE = np.uint16
FRAME = np.random.randint(0, 65535, size=FRAME_SHAPE, dtype=DTYPE)


class MyCamera(Camera):
    """Example Camera device."""

    def __init__(self) -> None:
        self._acquisition_thread: Union[threading.Thread, None] = None
        self._stop_event = threading.Event()

    def shape(self) -> tuple[int, int]:
        """Return the shape of the current camera state."""
        return FRAME_SHAPE

    def dtype(self) -> DTypeLike:
        """Return the data type of the current camera state."""
        return DTYPE

    def start_sequence(
        self,
        n: int,
        get_buffer: Callable[[], np.ndarray],
        notify: Callable[[Mapping], None],
    ) -> None:
        """Acquire a sequence of n images."""
        # Stop any existing acquisition
        self._stop_event.set()
        if self._acquisition_thread is not None:
            self._acquisition_thread.join()

        # Reset stop event for new acquisition
        self._stop_event.clear()

        # Start acquisition in background thread
        self._acquisition_thread = threading.Thread(
            target=self._acquire_images, args=(n, get_buffer, notify), daemon=True
        )
        self._acquisition_thread.start()

    def stop_sequence(self) -> None:
        """Stop the current sequence acquisition."""
        self._stop_event.set()
        if self._acquisition_thread is not None:
            self._acquisition_thread.join()
            self._acquisition_thread = None

    def _acquire_images(
        self,
        n: int,
        get_buffer: Callable[[], np.ndarray],
        notify: Callable[[Mapping], None],
    ) -> None:
        """Background thread method to acquire images."""
        for i in range(n):
            if self._stop_event.is_set():
                break

            buffer = get_buffer()
            time.sleep(0.01)  # Simulate time taken to acquire an image
            buffer[:] = FRAME
            notify({"random_key": f"value_{i}"})  # Example metadata, can be anything.


@pytest.mark.parametrize("device", ["python", "c++"])
def test_basic_acquisition(device: str) -> None:
    core = UniMMCore()
    assert not core.getCameraDevice()

    # load either a Python or C++ camera device
    if device == "python":
        camera = MyCamera()
        core.loadPyDevice(DEV, camera)
        core.initializeDevice(DEV)
    else:
        core.loadSystemConfiguration()

    core.setCameraDevice(DEV)
    assert core.getCameraDevice() == DEV
    assert (core.getImageWidth(), core.getImageHeight()) == FRAME_SHAPE
    assert core.getImageBitDepth() == FRAME.dtype.itemsize * 8
    assert core.getImageBufferSize() == FRAME.nbytes

    # Snap a single image
    core.snapImage()
    frame = core.getImage()
    assert frame.shape == FRAME_SHAPE
    assert frame.dtype == DTYPE

    # Start sequence acquisition
    assert core.getRemainingImageCount() == 0
    n_frames = 3
    core.startSequenceAcquisition(n_frames, 0, True)
    assert core.isSequenceRunning()

    while core.getRemainingImageCount() < n_frames:
        time.sleep(0.001)  # Sleep 1ms between checks

    # it should have stopped automatically once finished acquiring n_frames
    assert not core.isSequenceRunning()
    assert core.getRemainingImageCount() == n_frames

    last_image = core.getLastImage()

    for i in range(n_frames):
        frame, meta = core.popNextImageAndMD()
        if i == n_frames - 1:
            np.testing.assert_array_equal(frame, last_image)

        # assert meta[Keyword.Binning] == "1"
        # assert meta["Camera"] == "Camera"  # g_Keyword_Metadata_CameraLabel
        # assert meta["Height"] == str(FRAME_SHAPE[0])  # g_Keyword_Metadata_Height
        # assert meta["Width"] == str(FRAME_SHAPE[1])  # g_Keyword_Metadata_Width
        # assert meta[Keyword.PixelType] == "GRAY16"
        # assert meta[Keyword.Metadata_ImageNumber] == str(i)
        # assert Keyword.Elapsed_Time_ms in meta  # ElapsedTime-ms
        # assert "TimeReceivedByCore" in meta  # Metadata_TimeInCore_ms

        assert frame.shape == FRAME_SHAPE
        assert frame.dtype == DTYPE
        assert core.getRemainingImageCount() == n_frames - i - 1

    assert core.getRemainingImageCount() == 0
    with pytest.raises(IndexError):
        core.getLastImage()
    with pytest.raises(IndexError):
        core.popNextImage()
