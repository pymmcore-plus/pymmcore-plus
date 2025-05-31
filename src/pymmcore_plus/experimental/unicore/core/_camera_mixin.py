from __future__ import annotations

from datetime import datetime
from time import perf_counter_ns
from typing import TYPE_CHECKING, Any, Literal, overload

import numpy as np

from pymmcore_plus.core import Keyword as KW
from pymmcore_plus.core._constants import PixelType
from pymmcore_plus.core._metadata import Metadata
from pymmcore_plus.experimental.unicore.devices._camera import Camera

from ._base_mixin import UniCoreBase
from ._sequence_buffers import SeqState, SequenceBuffer

if TYPE_CHECKING:
    from collections.abc import Mapping

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

    def snapImage(self) -> None:
        if (cam := self._py_camera()) is None:  # fall back to C++
            return super().snapImage()

        shape, dtype = cam.shape(), cam.dtype()
        buf = np.empty(shape, dtype=dtype)
        self._current_image_buffer = buf

        cam.start_sequence(
            1,
            get_buffer=lambda: buf,
            notify=lambda _meta: None,
        )

    # --------------------------------------------------------------------- getImage

    @overload
    def getImage(self, *, fix: bool = True) -> np.ndarray: ...
    @overload
    def getImage(self, numChannel: int, *, fix: bool = True) -> np.ndarray: ...

    def getImage(
        self, numChannel: int | None = None, *, fix: bool = True
    ) -> np.ndarray:
        if (cam := self._py_camera()) is None:
            return (
                super().getImage(numChannel)
                if numChannel is not None
                else super().getImage()
            )

        if self._current_image_buffer is None:
            shape, dtype = cam.shape(), cam.dtype()
            self._current_image_buffer = np.zeros(shape, dtype=dtype)

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
            KW.Binning: "1",  # TODO
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

    @overload
    def startSequenceAcquisition(
        self, numImages: int, intervalMs: float, stopOnOverflow: bool
    ) -> None: ...

    @overload
    def startSequenceAcquisition(
        self,
        cameraLabel: DeviceLabel | str,
        numImages: int,
        intervalMs: float,
        stopOnOverflow: bool,
    ) -> None: ...

    def startSequenceAcquisition(self, *args: Any, **kw: Any) -> None:
        if len(args) == 3:  # current camera
            n, _interval, _stop = args
            if (cam := self._py_camera()) is None:
                return super().startSequenceAcquisition(*args, **kw)

            self._start_sequence(cam, n)

        elif len(args) == 4:  # explicit camera label
            label, n, _interval, _stop = args
            if (cam := self._py_camera(label)) is None:
                return super().startSequenceAcquisition(*args, **kw)

            self.setCameraDevice(label)
            self._start_sequence(cam, n)
        else:
            return super().startSequenceAcquisition(*args, **kw)

    # ------------------------------------------------------ continuous acquisition

    def startContinuousSequenceAcquisition(self, intervalMs: float = 0) -> None:
        if (cam := self._py_camera()) is None:
            return super().startContinuousSequenceAcquisition(intervalMs)

        self._start_sequence(cam, None)

    # ---------------------------------------------------------------- stopSequence

    def stopSequenceAcquisition(self, cameraLabel: str | None = None) -> None:
        if (cam := self._py_camera(cameraLabel)) is None:
            return super().stopSequenceAcquisition()

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
