from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable

import numpy as np
import pytest

import pymmcore_plus._pymmcore as pymmcore
from pymmcore_plus.core._constants import Keyword
from pymmcore_plus.experimental.unicore import CameraDevice
from pymmcore_plus.experimental.unicore.core._unicore import UniMMCore

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from numpy.typing import DTypeLike

DEV = "Camera"

np.random.seed(42)
FRAME_SHAPE = (512, 512)
DTYPE = np.uint16
FRAME = np.random.randint(0, 65535, size=FRAME_SHAPE, dtype=DTYPE)


class MyCamera(CameraDevice):
    """Example Camera device."""

    _exposure: float = 100.0

    def get_exposure(self) -> float:
        return self._exposure

    def set_exposure(self, exposure: float) -> None:
        """Set the exposure time in milliseconds."""
        self._exposure = exposure

    _binning: int = 1

    def get_binning(self) -> int:
        """Get the binning factor for the camera."""
        return self._binning

    def set_binning(self, value: int) -> None:
        self._binning = value

    def shape(self) -> tuple[int, int]:
        """Return the shape of the current camera state."""
        return FRAME_SHAPE

    def dtype(self) -> DTypeLike:
        """Return the data type of the current camera state."""
        return DTYPE

    def start_sequence(
        self,
        n: int | None,
        get_buffer: Callable[[Sequence[int], DTypeLike], np.ndarray],
    ) -> Iterator[Mapping]:
        """Start a sequence acquisition."""
        shape, dtype = self.shape(), self.dtype()
        if n is None:
            n = 2**63
        for i in range(n):
            buffer = get_buffer(shape, dtype)
            time.sleep(0.01)  # Simulate time taken to acquire an image
            buffer[:] = FRAME
            yield {"random_key": f"value_{i}"}  # Example metadata, can be anything.


class SequenceableCamera(MyCamera):
    """Camera device that supports exposure sequencing."""

    def __init__(self) -> None:
        super().__init__()
        self.set_property_sequence_max_length(Keyword.Exposure, 10)

    def load_exposure_sequence(self, sequence: Sequence[float]) -> None:
        """Load a sequence of exposure times."""
        self._exposure_sequence = tuple(sequence)

    def start_exposure_sequence(self) -> None:
        """Start the exposure sequence."""
        self._exposure_sequence_started = True

    def stop_exposure_sequence(self) -> None:
        """Stop the exposure sequence."""
        self._exposure_sequence_stopped = True


def _load_device(core: UniMMCore, device: str, cls: type = MyCamera) -> None:
    # load either a Python or C++ camera device
    if DEV in core.getLoadedDevices():
        core.unloadDevice(DEV)
    if device == "python":
        camera = cls()
        core.loadPyDevice(DEV, camera)
        core.initializeDevice(DEV)
    else:
        core.loadSystemConfiguration()

    core.setCameraDevice(DEV)
    assert core.getCameraDevice() == DEV


@pytest.mark.parametrize("device", ["python", "c++"])
def test_basic_properties(device: str) -> None:
    core = UniMMCore()

    # load either a Python or C++ camera device
    core.loadSystemConfiguration()
    _load_device(core, device)

    assert (core.getImageWidth(), core.getImageHeight()) == FRAME_SHAPE
    assert core.getImageBitDepth() == FRAME.dtype.itemsize * 8
    assert core.getImageBufferSize() == FRAME.nbytes
    assert core.getBytesPerPixel() == FRAME.dtype.itemsize
    assert core.getNumberOfComponents() == 1

    # exposure and binning
    core.setExposure(42.0)
    assert core.getExposure() == 42.0

    core.setProperty(DEV, Keyword.Binning, 2)
    assert str(core.getProperty(DEV, Keyword.Binning)) == "2"
    core.setProperty(DEV, Keyword.Binning, 1)

    assert not core.isExposureSequenceable(DEV)

    assert core.getPixelSizeAffine(False) == (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    assert core.getPixelSizeUm() == 1.0

    core.setProperty(DEV, Keyword.Binning, 2)
    assert core.getPixelSizeAffine(False) == (2.0, 0.0, 0.0, 0.0, 2.0, 0.0)
    assert core.getPixelSizeUm() == 2.0


@pytest.mark.parametrize("device", ["python", "c++"])
def test_basic_acquisition(device: str) -> None:
    core = UniMMCore()
    assert not core.getCameraDevice()

    # load either a Python or C++ camera device
    _load_device(core, device)

    with pytest.raises(RuntimeError, match=r"snapImage()"):
        core.getImage()

    # Snap a single image
    core.snapImage()
    frame = core.getImage()
    assert frame.shape == FRAME_SHAPE
    assert frame.dtype == DTYPE


@pytest.mark.parametrize("device", ["python", "c++"])
def test_sequence_acquisition(device: str) -> None:
    core = UniMMCore()

    # load either a Python or C++ camera device
    _load_device(core, device)

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

        assert meta[Keyword.Binning] == "1"
        assert meta[Keyword.Metadata_CameraLabel] == "Camera"
        assert meta[Keyword.Metadata_Height] == str(FRAME_SHAPE[0])
        assert meta[Keyword.Metadata_Width] == str(FRAME_SHAPE[1])
        assert meta[Keyword.PixelType] == "GRAY16"
        assert meta[Keyword.Metadata_ImageNumber] == str(i)
        assert Keyword.Elapsed_Time_ms in meta
        assert Keyword.Metadata_TimeInCore in meta
        if device == "python":
            assert meta["random_key"] == f"value_{i}"

        assert frame.shape == FRAME_SHAPE
        assert frame.dtype == DTYPE
        assert core.getRemainingImageCount() == n_frames - i - 1

    assert core.getRemainingImageCount() == 0

    # TODO: fix in pymmcore-nano the fact that it raises a different type of exception
    etype = Exception if pymmcore.NANO else IndexError
    with pytest.raises(etype, match="Circular buffer"):
        core.getLastImage()
    with pytest.raises(etype, match="Circular buffer"):
        core.popNextImage()


@pytest.mark.parametrize("device", ["python", "c++"])
def test_continuous_sequence_acquisition(device: str) -> None:
    core = UniMMCore()
    # load either a Python or C++ camera device
    _load_device(core, device)

    # Start continuous sequence acquisition
    core.startContinuousSequenceAcquisition()
    assert core.isSequenceRunning()
    while core.getRemainingImageCount() < 3:
        time.sleep(0.001)
    assert core.getRemainingImageCount() >= 3
    core.stopSequenceAcquisition()
    assert not core.isSequenceRunning()
    assert isinstance(core.getLastImage(), np.ndarray)
    assert isinstance(core.popNextImage(), np.ndarray)


def test_sequenceable_exposures() -> None:
    """Test camera mixin methods for exposure control and sequencing."""
    core = UniMMCore()

    camera = SequenceableCamera()
    core.loadPyDevice(DEV, camera)
    core.initializeDevice(DEV)

    assert core.isExposureSequenceable(DEV)
    assert core.getExposureSequenceMaxLength(DEV) == 10

    core.loadExposureSequence(DEV, [10.0, 20.0, 30.0])
    assert camera._exposure_sequence == (10.0, 20.0, 30.0)

    core.startExposureSequence(DEV)
    assert camera._exposure_sequence_started

    core.stopExposureSequence(DEV)
    assert camera._exposure_sequence_stopped


@pytest.mark.parametrize("device", ["python", "c++"])
def test_buffer_methods(device: str) -> None:
    core = UniMMCore()
    _load_device(core, device)

    # note: 250 is the default on C++, for python we patch this in conftest.py
    assert core.getCircularBufferMemoryFootprint() == 250
    core.setCircularBufferMemoryFootprint(10)
    assert core.getCircularBufferMemoryFootprint() == 10

    core.initializeCircularBuffer()
    assert core.getBufferFreeCapacity() == 20
    assert core.getBufferTotalCapacity() == 20

    core.startSequenceAcquisition(2, 0, True)
    while core.isSequenceRunning():
        time.sleep(0.001)
    assert core.getBufferFreeCapacity() == 18
    assert not core.isBufferOverflowed()

    core.startSequenceAcquisition(10000, 0, True)
    timeout = 5.0
    while core.isSequenceRunning():
        if timeout <= 0:
            raise RuntimeError("Buffer overflow did not occur within the timeout.")
        time.sleep(0.1)
        timeout -= 0.1
    assert core.isBufferOverflowed()
    core.clearCircularBuffer()


def test_multicamera_setup() -> None:
    """Test multi-camera setup and configuration."""
    core = UniMMCore()

    # Load multiple cameras
    cam1 = MyCamera()
    cam2 = MyCamera()
    core.loadPyDevice("cam1", cam1)
    core.loadPyDevice("cam2", cam2)
    core.initializeDevice("cam1")
    core.initializeDevice("cam2")

    # Test setup
    core.setup_multicamera(["cam1", "cam2"])
    assert core.getNumberOfCameraChannels() == 2
    assert core.getCameraChannelName(0) == "cam1"
    assert core.getCameraChannelName(1) == "cam2"
    assert core.getPhysicalCameraDevice(0) == "cam1"
    assert core.getPhysicalCameraDevice(1) == "cam2"

    # Test clear (by passing None)
    core.setup_multicamera(None)
    # After clearing, set one of the cameras as the current device
    core.setCameraDevice("cam1")
    assert core.getNumberOfCameraChannels() == 1

    # Test validation errors
    with pytest.raises(ValueError, match="not a loaded Python device"):
        core.setup_multicamera(["nonexistent"])

    core.loadPyDevice("notcam", MyCamera())
    # Device is loaded but not initialized, should still work
    core.setup_multicamera(["cam1", "notcam"])
    core.setup_multicamera(None)  # Clear again


def test_multicamera_snap() -> None:
    """Test multi-camera snap acquisition."""
    core = UniMMCore()

    # Load and setup multiple cameras
    core.loadPyDevice("cam1", MyCamera())
    core.loadPyDevice("cam2", MyCamera())
    core.initializeDevice("cam1")
    core.initializeDevice("cam2")
    core.setup_multicamera(["cam1", "cam2"])

    # Snap all cameras
    core.snapImage()

    # Retrieve images from each camera
    img1 = core.getImage(0)
    img2 = core.getImage(1)

    assert img1.shape == FRAME_SHAPE
    assert img2.shape == FRAME_SHAPE
    assert img1.dtype == DTYPE
    assert img2.dtype == DTYPE
    np.testing.assert_array_equal(img1, FRAME)
    np.testing.assert_array_equal(img2, FRAME)

    # Test error when channel out of range
    with pytest.raises(IndexError, match="out of range"):
        core.getImage(2)


def test_multicamera_sequence() -> None:
    """Test multi-camera sequence acquisition."""
    core = UniMMCore()

    # Load and setup multiple cameras
    core.loadPyDevice("cam1", MyCamera())
    core.loadPyDevice("cam2", MyCamera())
    core.initializeDevice("cam1")
    core.initializeDevice("cam2")
    core.setup_multicamera(["cam1", "cam2"])
    core.setCameraDevice("cam1")  # Set any as current

    # Start sequence acquisition
    n_frames = 3
    core.startSequenceAcquisition(n_frames, 0, True)
    assert core.isSequenceRunning()

    # Wait for images to arrive
    # With 2 cameras, we expect n_frames * 2 total images
    expected_total = n_frames * 2
    while core.getRemainingImageCount() < expected_total:
        time.sleep(0.001)
        if not core.isSequenceRunning():
            break

    # Should have stopped automatically
    assert not core.isSequenceRunning()
    assert core.getRemainingImageCount() == expected_total

    # Pop images - they should come from alternating cameras
    images_retrieved = 0
    cameras_seen = set()
    while core.getRemainingImageCount() > 0:
        frame, meta = core.popNextImageAndMD()
        images_retrieved += 1
        assert frame.shape == FRAME_SHAPE
        assert frame.dtype == DTYPE
        # Track which cameras we've seen - using the correct key name
        cam_label = meta.get("Camera", None)
        if cam_label is None:
            # Try alternative key
            cam_label = meta.get(core.Keyword.Metadata_CameraLabel, None)
        if cam_label:
            cameras_seen.add(cam_label)

    assert images_retrieved == expected_total
    # We should have seen images from both cameras
    assert len(cameras_seen) == 2
    assert "cam1" in cameras_seen
    assert "cam2" in cameras_seen


def test_multicamera_continuous_sequence() -> None:
    """Test multi-camera continuous sequence acquisition."""
    core = UniMMCore()

    # Load and setup multiple cameras
    core.loadPyDevice("cam1", MyCamera())
    core.loadPyDevice("cam2", MyCamera())
    core.initializeDevice("cam1")
    core.initializeDevice("cam2")
    core.setup_multicamera(["cam1", "cam2"])
    core.setCameraDevice("cam1")

    # Start continuous acquisition
    core.startContinuousSequenceAcquisition()
    assert core.isSequenceRunning()

    # Wait for some images
    while core.getRemainingImageCount() < 6:
        time.sleep(0.001)

    # Stop acquisition
    core.stopSequenceAcquisition()
    assert not core.isSequenceRunning()

    # Should have images from both cameras
    count = core.getRemainingImageCount()
    assert count >= 6

    # Verify we can pop images
    frame = core.popNextImage()
    assert frame.shape == FRAME_SHAPE


def test_multicamera_errors() -> None:
    """Test multi-camera error conditions."""
    core = UniMMCore()

    # Load cameras
    core.loadPyDevice("cam1", MyCamera())
    core.loadPyDevice("cam2", MyCamera())
    core.initializeDevice("cam1")
    core.initializeDevice("cam2")

    # Cannot setup multicamera while sequence is running
    core.loadPyDevice("single", MyCamera())
    core.initializeDevice("single")
    core.setCameraDevice("single")
    core.startContinuousSequenceAcquisition()

    with pytest.raises(RuntimeError, match="while sequence is running"):
        core.setup_multicamera(["cam1", "cam2"])

    core.stopSequenceAcquisition()

    # Now setup should work
    core.setup_multicamera(["cam1", "cam2"])

    # Cannot clear while sequence is running
    core.startContinuousSequenceAcquisition()
    with pytest.raises(RuntimeError, match="while sequence is running"):
        core.setup_multicamera(None)  # Try to clear
    core.stopSequenceAcquisition()
