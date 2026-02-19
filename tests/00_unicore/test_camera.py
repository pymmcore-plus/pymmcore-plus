from __future__ import annotations

import time
from typing import TYPE_CHECKING

import numpy as np
import pytest

import pymmcore_plus._pymmcore as pymmcore
from pymmcore_plus.core._constants import Keyword
from pymmcore_plus.experimental.unicore import CameraDevice, SimpleCameraDevice
from pymmcore_plus.experimental.unicore.core._unicore import UniMMCore

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    from numpy.typing import DTypeLike

DEV = "Camera"

np.random.seed(42)
SENSOR_SHAPE = (512, 512)
DTYPE = np.uint16
FRAME = np.random.randint(0, 65535, size=SENSOR_SHAPE, dtype=DTYPE)


class MyCamera(CameraDevice):
    """Camera device using CameraDevice directly with start_sequence()."""

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
        """Return the shape of the current image."""
        return SENSOR_SHAPE

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
            time.sleep(0.01)
            buffer[:] = FRAME
            yield {"random_key": f"value_{i}"}


class MySimpleCamera(SimpleCameraDevice):
    """Camera device using SimpleCameraDevice with snap()."""

    _exposure: float = 100.0

    def get_exposure(self) -> float:
        return self._exposure

    def set_exposure(self, exposure: float) -> None:
        self._exposure = exposure

    _binning: int = 1

    def get_binning(self) -> int:
        return self._binning

    def set_binning(self, value: int) -> None:
        self._binning = value

    def sensor_shape(self) -> tuple[int, int]:
        return SENSOR_SHAPE

    def dtype(self) -> DTypeLike:
        return DTYPE

    def snap(self, buffer: np.ndarray) -> Mapping:
        """Snap a single full-frame image."""
        time.sleep(0.01)
        buffer[:] = FRAME
        return {"random_key": "value"}


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

    assert (core.getImageWidth(), core.getImageHeight()) == SENSOR_SHAPE
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
    assert frame.shape == SENSOR_SHAPE
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
        assert meta[Keyword.Metadata_Height] == str(SENSOR_SHAPE[0])
        assert meta[Keyword.Metadata_Width] == str(SENSOR_SHAPE[1])
        assert meta[Keyword.PixelType] == "GRAY16"
        assert meta[Keyword.Metadata_ImageNumber] == str(i)
        assert Keyword.Elapsed_Time_ms in meta
        assert Keyword.Metadata_TimeInCore in meta
        if device == "python":
            assert meta["random_key"] == f"value_{i}"

        assert frame.shape == SENSOR_SHAPE
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


@pytest.mark.parametrize("device", ["python", "c++"])
def test_roi(device: str) -> None:
    """getROI/setROI/clearROI round-trip, including snapped image size."""
    core = UniMMCore()
    # Use SimpleCameraDevice for python (supports software ROI)
    cls = MySimpleCamera if device == "python" else MyCamera
    _load_device(core, device, cls=cls)

    # full frame by default
    assert list(core.getROI()) == [0, 0, *SENSOR_SHAPE[::-1]]
    assert list(core.getROI(DEV)) == [0, 0, *SENSOR_SHAPE[::-1]]

    core.snapImage()
    full = core.getImage()
    assert full.shape == SENSOR_SHAPE

    # set a sub-ROI — image dimensions should change
    core.setROI(10, 20, 100, 200)
    assert list(core.getROI()) == [10, 20, 100, 200]

    core.snapImage()
    cropped = core.getImage()
    assert cropped.shape == (200, 100)

    # clear resets to full frame
    core.clearROI()
    assert list(core.getROI()) == [0, 0, *SENSOR_SHAPE[::-1]]

    core.snapImage()
    restored = core.getImage()
    assert restored.shape == SENSOR_SHAPE


def test_simple_camera_roi() -> None:
    """SimpleCameraDevice auto-crops via snap()."""
    core = UniMMCore()
    _load_device(core, "python", cls=MySimpleCamera)

    # full frame by default
    core.snapImage()
    assert core.getImage().shape == SENSOR_SHAPE

    # set ROI — snap should auto-crop
    core.setROI(10, 20, 100, 200)
    assert list(core.getROI()) == [10, 20, 100, 200]

    core.snapImage()
    cropped = core.getImage()
    assert cropped.shape == (200, 100)
    np.testing.assert_array_equal(cropped, FRAME[20:220, 10:110])

    # sequence acquisition should also auto-crop
    core.startSequenceAcquisition(2, 0, True)
    while core.isSequenceRunning():
        time.sleep(0.001)
    frame, _meta = core.popNextImageAndMD()
    assert frame.shape == (200, 100)
    np.testing.assert_array_equal(frame, FRAME[20:220, 10:110])

    # clear resets
    core.clearROI()
    core.snapImage()
    assert core.getImage().shape == SENSOR_SHAPE


def test_base_camera_set_roi_raises() -> None:
    """CameraDevice.set_roi() raises NotImplementedError by default."""
    cam = MyCamera()
    # get_roi works (returns full frame)
    assert cam.get_roi() == (0, 0, 512, 512)
    # set_roi raises
    with pytest.raises(NotImplementedError, match="does not support setting ROI"):
        cam.set_roi(10, 20, 100, 200)
    # clear_roi is a no-op
    cam.clear_roi()


def test_camera_channels_numbers() -> None:
    """
    Test the function to return the numbers of camera channels.
    """
    core = UniMMCore()

    core.loadPyDevice(DEV, MyCamera())
    core.initializeDevice(DEV)

    core.setCameraDevice(DEV)
    assert core.getCameraDevice() == DEV

    assert core.getNumberOfCameraChannels() == 1
