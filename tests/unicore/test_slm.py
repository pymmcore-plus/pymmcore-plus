from collections.abc import Sequence
from typing import Any

import numpy as np
import pytest
from numpy.typing import DTypeLike

from pymmcore_plus.experimental.unicore import SLMDevice
from pymmcore_plus.experimental.unicore.core._unicore import UniMMCore

DEV = "SLM"

np.random.seed(42)
SLM_SHAPE = (512, 512)
SLM_COLOR_SHAPE = (256, 256, 3)  # RGB SLM
DTYPE = np.uint8
TEST_IMAGE = np.random.randint(0, 255, size=SLM_SHAPE, dtype=DTYPE)
TEST_COLOR_IMAGE = np.random.randint(0, 255, size=SLM_COLOR_SHAPE, dtype=DTYPE)


class MySLM(SLMDevice):
    """Example SLM device."""

    def __init__(self, color: bool = False) -> None:
        super().__init__()
        self._exposure: float = 1000.0  # milliseconds
        self._color = color
        self._current_image: np.ndarray | None = None
        self._image_displayed = False

    def shape(self) -> tuple[int, ...]:
        """Return the shape of the SLM image buffer."""
        return SLM_COLOR_SHAPE if self._color else SLM_SHAPE

    def dtype(self) -> DTypeLike:
        """Return the data type of the image buffer."""
        return DTYPE

    def set_image(self, pixels: np.ndarray) -> None:
        """Load the image into the SLM device adapter."""
        self._current_image = pixels.copy()
        self._image_displayed = False

    def get_image(self) -> np.ndarray:
        """Get the current image from the SLM device adapter."""
        if self._current_image is None:
            raise RuntimeError("No image loaded")
        return self._current_image

    def display_image(self) -> None:
        """Command the SLM to display the loaded image."""
        if self._current_image is None:
            raise RuntimeError("No image loaded")
        self._image_displayed = True

    def set_exposure(self, interval_ms: float) -> None:
        """Command the SLM to turn off after a specified interval."""
        self._exposure = interval_ms

    def get_exposure(self) -> float:
        """Find out the exposure interval of an SLM."""
        return self._exposure


class SequenceableSLM(MySLM):
    """SLM device that supports image sequencing."""

    def __init__(self, color: bool = False) -> None:
        super().__init__(color)
        self._sequence_max_length = 10
        self._image_sequence: tuple[np.ndarray, ...] = ()
        self._sequence_running = False

    def get_sequence_max_length(self) -> int:
        """Return the maximum length of an image sequence that can be uploaded."""
        return self._sequence_max_length

    def send_sequence(self, sequence: Sequence[np.ndarray]) -> None:
        """Load a sequence of images to the SLM."""
        self._image_sequence = tuple(sequence)

    def start_sequence(self) -> None:
        """Start a sequence of images on the SLM."""
        if not self._image_sequence:
            raise RuntimeError("No sequence loaded")
        self._sequence_running = True

    def stop_sequence(self) -> None:
        """Stop a sequence of images on the SLM."""
        self._sequence_running = False


def _load_slm_device(
    core: UniMMCore, device: str, cls: type = MySLM, **kwargs: Any
) -> None:
    """Load either a Python or C++ SLM device."""
    if DEV in core.getLoadedDevices():
        core.unloadDevice(DEV)

    if device == "python":
        slm = cls(**kwargs)
        core.loadPyDevice(DEV, slm)
        core.initializeDevice(DEV)
    else:
        # For C++ device, we'd load from system configuration
        # but for now we'll skip C++ tests since we don't have a C++ SLM in the demo
        # config
        pytest.skip("C++ SLM device not available in demo configuration")

    core.setSLMDevice(DEV)
    assert core.getSLMDevice() == DEV


@pytest.mark.parametrize("device", ["python"])  # Only python for now
def test_basic_slm_properties(device: str) -> None:
    """Test basic SLM properties like dimensions, data type, etc."""
    core = UniMMCore()
    _load_slm_device(core, device)

    # Test basic dimensions
    assert core.getSLMWidth() == SLM_SHAPE[1]  # width is second dimension
    assert core.getSLMHeight() == SLM_SHAPE[0]  # height is first dimension
    assert core.getSLMNumberOfComponents() == 1  # grayscale
    assert core.getSLMBytesPerPixel() == np.dtype(DTYPE).itemsize

    # Test with color SLM
    core.unloadDevice(DEV)
    _load_slm_device(core, device, MySLM, color=True)

    assert core.getSLMWidth() == SLM_COLOR_SHAPE[1]
    assert core.getSLMHeight() == SLM_COLOR_SHAPE[0]
    assert core.getSLMNumberOfComponents() == 3  # RGB


@pytest.mark.parametrize("device", ["python"])
def test_slm_image_operations(device: str) -> None:
    """Test SLM image loading and display operations."""
    core = UniMMCore()
    _load_slm_device(core, device)

    # Test setting a uniform pixel value
    core.setSLMPixelsTo(128)  # Set all pixels to intensity 128

    # Test setting an image
    core.setSLMImage(TEST_IMAGE)

    # Test displaying the image
    core.displaySLMImage()

    # Test with color SLM
    core.unloadDevice(DEV)
    _load_slm_device(core, device, MySLM, color=True)

    # Test RGB uniform values
    core.setSLMPixelsTo(255, 128, 64)  # Set all pixels to RGB(255, 128, 64)

    # Test setting color image
    core.setSLMImage(TEST_COLOR_IMAGE)
    core.displaySLMImage()


@pytest.mark.parametrize("device", ["python"])
def test_slm_exposure_control(device: str) -> None:
    """Test SLM exposure control."""
    core = UniMMCore()
    _load_slm_device(core, device)

    # Test setting and getting exposure
    initial_exposure = core.getSLMExposure()
    assert initial_exposure == 1000.0  # default from MySLM

    core.setSLMExposure(500.0)
    assert core.getSLMExposure() == 500.0

    core.setSLMExposure(2000.0)
    assert core.getSLMExposure() == 2000.0


@pytest.mark.parametrize("device", ["python"])
def test_slm_device_management(device: str) -> None:
    """Test SLM device management (set/get SLM device)."""
    core = UniMMCore()

    # Initially no SLM device
    assert core.getSLMDevice() == ""

    _load_slm_device(core, device)

    # Should now have the SLM device set
    assert core.getSLMDevice() == DEV


def test_slm_sequences() -> None:
    """Test SLM sequence operations."""
    core = UniMMCore()

    # Use sequenceable SLM
    slm = SequenceableSLM()
    core.loadPyDevice(DEV, slm)
    core.initializeDevice(DEV)
    core.setSLMDevice(DEV)

    # Test sequence max length
    assert core.getSLMSequenceMaxLength(DEV) == 10

    # Create a sequence of test images
    sequence_images = []
    for i in range(3):
        img = np.full(
            SLM_SHAPE, i * 50, dtype=DTYPE
        )  # Different intensity for each image
        sequence_images.append(img.tobytes())

    # Test loading sequence
    core.loadSLMSequence(DEV, sequence_images)
    assert len(slm._image_sequence) == 3

    # Test starting sequence
    core.startSLMSequence(DEV)
    assert slm._sequence_running

    # Test stopping sequence
    core.stopSLMSequence(DEV)
    assert not slm._sequence_running


def test_slm_sequences_color() -> None:
    """Test SLM sequence operations with color images."""
    core = UniMMCore()

    # Use color sequenceable SLM
    slm = SequenceableSLM(color=True)
    core.loadPyDevice(DEV, slm)
    core.initializeDevice(DEV)
    core.setSLMDevice(DEV)

    # Create a sequence of color test images
    sequence_images = []
    for _i in range(2):
        img = np.random.randint(0, 255, size=SLM_COLOR_SHAPE, dtype=DTYPE)
        sequence_images.append(img.tobytes())

    # Test loading and running color sequence
    core.loadSLMSequence(DEV, sequence_images)
    core.startSLMSequence(DEV)
    assert slm._sequence_running

    core.stopSLMSequence(DEV)
    assert not slm._sequence_running


@pytest.mark.parametrize("device", ["python"])
def test_slm_with_device_label(device: str) -> None:
    """Test SLM operations with explicit device label."""
    core = UniMMCore()
    _load_slm_device(core, device)

    # Test all operations with explicit device label
    core.setSLMExposure(DEV, 750.0)
    assert core.getSLMExposure(DEV) == 750.0

    assert core.getSLMWidth(DEV) == SLM_SHAPE[1]
    assert core.getSLMHeight(DEV) == SLM_SHAPE[0]
    assert core.getSLMNumberOfComponents(DEV) == 1
    assert core.getSLMBytesPerPixel(DEV) == np.dtype(DTYPE).itemsize

    core.setSLMPixelsTo(DEV, 200)
    core.setSLMImage(DEV, TEST_IMAGE)
    core.displaySLMImage(DEV)
    assert np.array_equal(core.getSLMImage(DEV), TEST_IMAGE)


def test_slm_sequence_errors() -> None:
    """Test SLM sequence error conditions."""
    core = UniMMCore()

    # Test with non-sequenceable SLM (basic MySLM)
    core.loadPyDevice(DEV, MySLM())
    core.initializeDevice(DEV)
    core.setSLMDevice(DEV)

    # Should return 0 for max sequence length (not supported)
    assert core.getSLMSequenceMaxLength(DEV) == 0

    # Should raise RuntimeError for sequence operations
    with pytest.raises(RuntimeError, match="does not support sequences"):
        core.loadSLMSequence(DEV, (TEST_IMAGE,))

    with pytest.raises(RuntimeError, match="does not support sequences"):
        core.startSLMSequence(DEV)

    with pytest.raises(RuntimeError, match="does not support sequences"):
        core.stopSLMSequence(DEV)


def test_slm_image_validation() -> None:
    """Test SLM image validation."""
    core = UniMMCore()

    core.loadPyDevice(DEV, MySLM())
    core.initializeDevice(DEV)
    core.setSLMDevice(DEV)

    # Test display without image
    with pytest.raises(RuntimeError, match="No image loaded"):
        core.displaySLMImage(DEV)

    # Test with wrong shape image
    wrong_shape_image = np.random.randint(0, 255, size=(100, 100), dtype=DTYPE)
    with pytest.raises(ValueError, match="Image shape .* doesn't match SLM shape"):
        core.setSLMImage(DEV, wrong_shape_image)


def test_sequenceable_slm_validation() -> None:
    """Test SequenceableSLM validation."""
    core = UniMMCore()

    core.loadPyDevice(DEV, SequenceableSLM())
    core.initializeDevice(DEV)
    core.setSLMDevice(DEV)

    # Test start sequence without loading
    with pytest.raises(RuntimeError, match="No sequence loaded"):
        core.startSLMSequence(DEV)

    # Test sequence too long
    long_sequence = tuple(TEST_IMAGE for _ in range(15))  # max is 10
    with pytest.raises(ValueError, match="Sequence length 15 exceeds maximum 10"):
        core.loadSLMSequence(DEV, long_sequence)

    # Test sequence with wrong image shape
    wrong_shape_sequence = (np.random.randint(0, 255, size=(100, 100), dtype=DTYPE),)
    with pytest.raises(
        ValueError,
        match=r"Image 0 shape \(100, 100\) does not match SLM shape \(512, 512\)",
    ):
        core.loadSLMSequence(DEV, wrong_shape_sequence)
