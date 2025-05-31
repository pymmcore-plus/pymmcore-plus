from __future__ import annotations

from datetime import datetime
from time import perf_counter_ns
from typing import TYPE_CHECKING, Any, Literal, overload

import numpy as np

import pymmcore_plus._pymmcore as pymmcore
from pymmcore_plus.core import Keyword as KW
from pymmcore_plus.core._constants import PixelType
from pymmcore_plus.core._metadata import Metadata
from pymmcore_plus.experimental.unicore.devices._camera import Camera

from ._base_mixin import UniCoreBase
from ._sequence_buffers import SeqState, SequenceBuffer

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from pymmcore import DeviceLabel


class PyCameraMixin(UniCoreBase):
    """Overrides MMCore camera calls when the device is a Python adapter."""

    # attributes created on-demand
    _current_image_buffer: np.ndarray | None = None
    _seq: SequenceBuffer | None = None

    # --------------------------------------------------------------------- utils

    def _py_camera(self, cameraLabel: str | None = None) -> Camera | None:
        """Return the *Python* Camera for ``label`` (or current), else ``None``."""
        label = cameraLabel or self.getCameraDevice()
        if label in self._pydevices:
            return self._pydevices.get_device_of_type(label, Camera)
        return None

    def setCameraDevice(self, cameraLabel: DeviceLabel | str) -> None:
        """Set the camera device."""
        label = self._set_current_if_pydevice(KW.CoreCamera, cameraLabel)
        super().setCameraDevice(label)

    def getCameraDevice(self) -> DeviceLabel | Literal[""]:
        """Returns the label of the currently selected camera device.

        Returns empty string if no camera device is selected.
        """
        return self._pycore.current(KW.CoreCamera) or super().getCameraDevice()

    # --------------------------------------------------------------------- snap

    def _do_snap_image(self) -> None:
        if (cam := self._py_camera()) is None:
            return pymmcore.CMMCore.snapImage(self)

        buf = np.empty(cam.shape(), dtype=cam.dtype())
        # synchronous call - consume one item from the generator
        for _ in cam.start_sequence(1, get_buffer=lambda: buf):
            self._current_image_buffer = buf
            return

    # --------------------------------------------------------------------- getImage

    @overload
    def getImage(self, *, fix: bool = True) -> np.ndarray: ...
    @overload
    def getImage(self, numChannel: int, *, fix: bool = True) -> np.ndarray: ...

    def getImage(
        self, numChannel: int | None = None, *, fix: bool = True
    ) -> np.ndarray:
        if self._py_camera() is None:
            if numChannel is not None:
                return super().getImage(numChannel, fix=fix)
            return super().getImage(fix=fix)

        if self._current_image_buffer is None:
            raise RuntimeError(
                "No image buffer available. Call snapImage() before calling getImage()."
            )

        return self._current_image_buffer

    # ---------------------------------------------------------------- sequence common

    def _start_sequence(self, cam: Camera, n_images: int | None) -> None:
        """Initialise _seq state and call cam.start_sequence."""
        shape, dtype = cam.shape(), np.dtype(cam.dtype())
        camera_label = cam.get_label()

        self._seq = _seq = SeqState(shape, dtype, n_images)
        # Set acquisition start time for elapsed time calculation

        n_components = shape[2] if len(shape) > 2 else 1
        base_meta: dict[str, Any] = {
            KW.Binning: cam.get_property_value(KW.Binning),
            KW.Metadata_CameraLabel: camera_label,
            KW.Metadata_Height: str(shape[0]),
            KW.Metadata_Width: str(shape[1]),
            KW.Metadata_ROI_X: "0",
            KW.Metadata_ROI_Y: "0",
            KW.PixelType: PixelType.for_bytes(dtype.itemsize, n_components),
        }

        # Create metadata-injecting wrapper for notify callback
        # TODO: decide if metadata goes on SeqState or stays here.
        def notify_with_metadata(cam_meta: Mapping) -> None:
            elapsed_ms = (perf_counter_ns() - start_time) / 1e6
            received = datetime.now().isoformat(sep=" ")
            base_meta.update(
                {
                    **cam_meta,
                    KW.Metadata_TimeInCore: received,
                    KW.Metadata_ImageNumber: str(_seq.acquired),
                    KW.Elapsed_Time_ms: f"{elapsed_ms:.2f}",
                }
            )
            _seq.notify(base_meta)

        start_time = perf_counter_ns()
        # TODO: should we use None or a large number.  Large number is more consistent
        # for Camera Device Adapters, but hides details from the adapter.
        cam.start_sequence_thread(
            n_images or 2**63 - 1, _seq.get_buffer, notify_with_metadata
        )

    # ------------------------------------------------------- startSequenceAcquisition

    def _do_start_sequence_acquisition(
        self, cameraLabel: str, numImages: int, intervalMs: float, stopOnOverflow: bool
    ) -> None:
        if (cam := self._py_camera(cameraLabel)) is None:
            return pymmcore.CMMCore.startSequenceAcquisition(
                self, cameraLabel, numImages, intervalMs, stopOnOverflow
            )

        self._start_sequence(cam, numImages)

    # ------------------------------------------------------ continuous acquisition

    def _do_start_continuous_sequence_acquisition(self, intervalMs: float = 0) -> None:
        if (cam := self._py_camera()) is None:
            return pymmcore.CMMCore.startContinuousSequenceAcquisition(self, intervalMs)

        self._start_sequence(cam, None)

    # ---------------------------------------------------------------- stopSequence

    def _do_stop_sequence_acquisition(self, cameraLabel: str) -> None:
        if (cam := self._py_camera(cameraLabel)) is None:
            return pymmcore.CMMCore.stopSequenceAcquisition(self, cameraLabel)

        cam.stop_sequence()
        if self._seq:
            self._seq.running = False

    # ------------------------------------------------------------------ queries
    @overload
    def isSequenceRunning(self) -> bool: ...
    @overload
    def isSequenceRunning(self, cameraLabel: DeviceLabel | str) -> bool: ...
    def isSequenceRunning(self, cameraLabel: DeviceLabel | str | None = None) -> bool:
        if self._py_camera(cameraLabel) is None:
            return super().isSequenceRunning()

        return bool(self._seq is not None and self._seq.running)

    def getRemainingImageCount(self) -> int:
        if self._py_camera() is None:
            return super().getRemainingImageCount()
        return len(self._seq) if self._seq is not None else 0

    def getLastImage(self) -> np.ndarray:
        if self._py_camera() is None:
            return super().getLastImage()
        if not (self._seq):
            raise IndexError("Circular buffer is empty.")
        return self._seq.buffers[-1]

    # ---------------------------------------------------- popNext helpers

    def popNextImage(self, *, fix: bool = True) -> np.ndarray:
        if self._py_camera() is None:
            return super().popNextImage(fix=fix)
        if not self._seq or not (data := self._seq.pop_left()):
            raise IndexError("Circular buffer is empty.")
        return data[0]

    def popNextImageAndMD(
        self, channel: int = 0, slice: int = 0, *, fix: bool = True
    ) -> tuple[np.ndarray, Metadata]:
        if self._py_camera() is None:
            return super().popNextImageAndMD(channel, slice, fix=fix)
        if not self._seq or not (data := self._seq.pop_left()):
            raise IndexError("Circular buffer is empty.")
        img, md = data
        return (img, Metadata(md))

    # ----------------------------------------------------------------- image info

    def getImageBitDepth(self) -> int:
        if (cam := self._py_camera()) is None:
            return super().getImageBitDepth()
        dtype = np.dtype(cam.dtype())
        return dtype.itemsize * 8

    def getBytesPerPixel(self) -> int:
        if (cam := self._py_camera()) is None:
            return super().getBytesPerPixel()
        dtype = np.dtype(cam.dtype())
        return dtype.itemsize

    def getImageBufferSize(self) -> int:
        if (cam := self._py_camera()) is None:
            return super().getImageBufferSize()
        shape, dtype = cam.shape(), np.dtype(cam.dtype())
        return int(np.prod(shape) * dtype.itemsize)

    def getImageHeight(self) -> int:
        if (cam := self._py_camera()) is None:
            return super().getImageHeight()
        return cam.shape()[0]

    def getImageWidth(self) -> int:
        if (cam := self._py_camera()) is None:
            return super().getImageWidth()
        return cam.shape()[1]

    def getNumberOfComponents(self) -> int:
        if (cam := self._py_camera()) is None:
            return super().getNumberOfComponents()
        shape = cam.shape()
        return 1 if len(shape) == 2 else shape[2]

    def getNumberOfCameraChannels(self) -> int:
        if self._py_camera() is None:
            return super().getNumberOfCameraChannels()
        raise NotImplementedError(
            "getNumberOfCameraChannels is not implemented for Python cameras."
        )

    def getCameraChannelName(self, channelNr: int) -> str:
        """Get the name of the camera channel."""
        if self._py_camera() is None:
            return super().getCameraChannelName(channelNr)
        raise NotImplementedError(
            "getCameraChannelName is not implemented for Python cameras."
        )

    def _get_binning(self, cameraLabel: DeviceLabel | str | None = None) -> int:
        """Get the binning for the camera."""
        if cam := self._py_camera(cameraLabel):
            with cam:
                return cam.get_binning()
        return 1

    @overload
    def getExposure(self) -> float: ...
    @overload
    def getExposure(self, cameraLabel: DeviceLabel | str, /) -> float: ...
    def getExposure(self, cameraLabel: DeviceLabel | str | None = None) -> float:
        """Get the exposure time in milliseconds."""
        if cam := self._py_camera(cameraLabel):
            with cam:
                return cam.get_exposure()
        if cameraLabel is None:
            return super().getExposure()
        return super().getExposure(cameraLabel)

    @overload
    def setExposure(self, exp: float, /) -> None: ...
    @overload
    def setExposure(self, cameraLabel: DeviceLabel | str, dExp: float, /) -> None: ...
    def setExposure(
        self, exp_or_label: str | float, exp_: float | None = None, /
    ) -> None:
        """Set the exposure time in milliseconds."""
        if isinstance(exp_or_label, str) and isinstance(exp_, float):
            if (cam := self._py_camera(exp_or_label)) is None:
                return super().setExposure(exp_or_label, exp_)
            with cam:
                cam.set_exposure(exp_)
        elif isinstance(exp_or_label, float) and exp_ is None:
            if (cam := self._py_camera()) is None:
                return super().setExposure(exp_or_label)
            with cam:
                cam.set_exposure(exp_or_label)
        else:
            raise TypeError(
                "setExposure must be called with either (exp: float) or "
                "(cameraLabel: str, exp: float)."
            )

    def isExposureSequenceable(self, cameraLabel: DeviceLabel | str) -> bool:
        """Check if the camera supports exposure sequences."""
        if (cam := self._py_camera(cameraLabel)) is None:
            return super().isExposureSequenceable(cameraLabel)
        return cam.is_property_sequenceable(KW.Exposure)

    def loadExposureSequence(
        self, cameraLabel: DeviceLabel | str, exposureSequence_ms: Sequence[float]
    ) -> None:
        """Transfer a sequence of exposure times to the camera."""
        if (cam := self._py_camera(cameraLabel)) is None:
            return super().loadExposureSequence(cameraLabel, exposureSequence_ms)
        cam.load_property_sequence(KW.Exposure, exposureSequence_ms)

    def getExposureSequenceMaxLength(self, cameraLabel: DeviceLabel | str) -> int:
        """Get the maximum length of the exposure sequence."""
        if (cam := self._py_camera(cameraLabel)) is None:
            return super().getExposureSequenceMaxLength(cameraLabel)
        return cam.get_property_info(KW.Exposure).sequence_max_length

    def startExposureSequence(self, cameraLabel: DeviceLabel | str) -> None:
        """Start a sequence of exposures."""
        if (cam := self._py_camera(cameraLabel)) is None:
            return super().startExposureSequence(cameraLabel)
        cam.start_property_sequence(KW.Exposure)

    def stopExposureSequence(self, cameraLabel: DeviceLabel | str) -> None:
        """Stop a sequence of exposures."""
        if (cam := self._py_camera(cameraLabel)) is None:
            return super().stopExposureSequence(cameraLabel)
        cam.stop_property_sequence(KW.Exposure)

    def prepareSequenceAcquisition(self, cameraLabel: DeviceLabel | str) -> None:
        """Prepare the camera for sequence acquisition."""
        if self._py_camera(cameraLabel) is None:
            return super().prepareSequenceAcquisition(cameraLabel)
        pass  # TODO: Implement prepareSequenceAcquisition for Python cameras?


# 	clearROI
# 	getROI
# 	getMultiROI
# 	setMultiROI
# 	setROI
# 	isMultiROIEnabled
# 	isMultiROISupported

# 	initializeCircularBuffer
# 	setCircularBufferMemoryFootprint

# 	getPixelSizeAffine
# 	getPixelSizeUm
