"""Multi-camera management for Unicore.

This module provides core-level multi-camera coordination, allowing multiple
Python cameras to be used as if they were a single multi-channel camera.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from ._sequence_buffer import SequenceBuffer

if TYPE_CHECKING:
    import numpy as np

    from ._unicore import AcquisitionThread, UniMMCore

_DEFAULT_BUFFER_SIZE_MB = 1000


class MultiCameraManager:
    """Manages multi-camera acquisition for Unicore.

    This class coordinates multiple Python cameras by delegating to the core's
    _start_sequence method with separate buffers and events per camera.

    Parameters
    ----------
    core : UniMMCore
        The core instance to delegate camera operations to.
    """

    def __init__(self, core: UniMMCore) -> None:
        self._core = core
        self._labels: tuple[str, ...] = ()
        self._lock = threading.RLock()  # Protect state modifications

        # Per-camera resources for snap acquisition
        self._snap_buffers: dict[str, np.ndarray | None] = {}

        # Per-camera resources for sequence acquisition
        self._seq_buffers: dict[str, SequenceBuffer] = {}
        self._stop_events: dict[str, threading.Event] = {}
        self._acquisition_threads: dict[str, AcquisitionThread] = {}
        self._last_popped_idx = -1  # For round-robin image retrieval

    def is_active(self) -> bool:
        """Return True if multi-camera mode is currently active."""
        with self._lock:
            return bool(self._labels)

    def setup(self, camera_labels: tuple[str, ...]) -> None:
        """Configure multi-camera mode with the given camera labels.

        Parameters
        ----------
        camera_labels : tuple[str, ...]
            Tuple of camera device labels to coordinate.
        """
        self._labels = camera_labels

        # Create per-camera resources
        for label in camera_labels:
            self._snap_buffers[label] = None
            self._seq_buffers[label] = SequenceBuffer(size_mb=_DEFAULT_BUFFER_SIZE_MB)
            self._stop_events[label] = threading.Event()

    def clear(self) -> None:
        """Clear multi-camera configuration."""
        self._labels = ()
        self._snap_buffers.clear()
        self._seq_buffers.clear()
        self._stop_events.clear()
        self._acquisition_threads.clear()

    def get_num_channels(self) -> int:
        """Return the number of camera channels."""
        return len(self._labels)

    def get_channel_name(self, idx: int) -> str:
        """Return the name of the camera channel at the given index."""
        if 0 <= idx < len(self._labels):
            return self._labels[idx]
        raise IndexError(f"Channel {idx} out of range")

    # -----------------------------------------------------------------------
    # Snap Acquisition
    # -----------------------------------------------------------------------

    def snap(self) -> None:
        """Snap images from all cameras in parallel."""
        # Import CameraDevice here to avoid circular imports

        with self._lock:
            labels = self._labels

        # Snap all cameras in parallel using the core's helper method
        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(self._snap_single_camera, label) for label in labels
            ]
            # Wait for all to complete
            for future in as_completed(futures):
                label, buf = future.result()
                if buf is not None:
                    self._snap_buffers[label] = buf

    def _snap_single_camera(self, label: str) -> tuple[str, np.ndarray | None]:
        """Snap a single camera using the core's helper method."""
        from pymmcore_plus.experimental.unicore.devices._camera import CameraDevice

        cam = self._core._pydevices.get_device_of_type(label, CameraDevice)  # noqa: SLF001
        buf = self._core._snap_single_camera(cam)  # noqa: SLF001
        return label, buf

    def get_snap_image(self, channel: int) -> np.ndarray:
        """Get the snapped image for the given channel.

        Returns
        -------
        np.ndarray
            The snapped image buffer for the specified channel.

        Raises
        ------
        IndexError
            If channel is out of range.
        RuntimeError
            If no image is available (snap not called).
        """
        with self._lock:
            if not (0 <= channel < len(self._labels)):
                raise IndexError(f"Channel {channel} out of range")

            label = self._labels[channel]
            buf = self._snap_buffers.get(label)

        if buf is None:
            raise RuntimeError(
                f"No image buffer available for camera {label!r}. "
                "Call snapImage() before calling getImage()."
            )
        return buf

    # -----------------------------------------------------------------------
    # Sequence Acquisition
    # -----------------------------------------------------------------------

    def start_sequence(self, n_images: int | None, stop_on_overflow: bool) -> None:
        """Start sequence acquisition for all cameras.

        Each camera gets its own buffer, event, and thread via _start_sequence.
        """
        # Import CameraDevice here to avoid circular imports
        from pymmcore_plus.experimental.unicore.devices._camera import CameraDevice

        with self._lock:
            # Validate all cameras before starting any
            for label in self._labels:
                if self._core.deviceBusy(label):
                    raise RuntimeError(f"Camera {label} is busy")

            # Clear stop events from previous acquisitions
            for label in self._labels:
                self._stop_events[label].clear()

            # Temporarily disable multi-camera mode
            saved_labels = self._labels
            self._labels = ()

        # Create threads for all cameras (but don't start yet)
        threads_to_start: list[tuple[str, AcquisitionThread]] = []

        try:
            # Start each camera's sequence acquisition using the core's logic
            for label in saved_labels:
                cam = self._core._pydevices.get_device_of_type(label, CameraDevice)  # noqa: SLF001
                with cam:
                    thread = self._core._create_sequence_thread(  # noqa: SLF001
                        cam=cam,
                        n_images=n_images,
                        stop_on_overflow=stop_on_overflow,
                        seq_buffer=self._seq_buffers[label],
                        stop_event=self._stop_events[label],
                    )
                    threads_to_start.append((label, thread))

            # All threads created successfully, now store and start them
            with self._lock:
                for label, thread in threads_to_start:
                    self._acquisition_threads[label] = thread
                    thread.start()
        except Exception:
            # If anything failed, clean up threads that were created
            for _ in threads_to_start:
                # Threads not started yet, just discard them
                pass
            raise
        finally:
            with self._lock:
                self._labels = saved_labels

    def stop_sequence(self) -> None:
        """Stop sequence acquisition for all cameras."""
        if not self._acquisition_threads:
            return

        # Signal all cameras to stop
        for label in self._labels:
            self._stop_events[label].set()

        # Wait for all threads to finish
        for thread in self._acquisition_threads.values():
            thread.join()

        self._acquisition_threads.clear()

    def is_sequence_running(self) -> bool:
        """Return True if any camera is still acquiring."""
        if not self._acquisition_threads:
            return False

        # Check if any thread is still alive
        any_alive = any(t.is_alive() for t in self._acquisition_threads.values())
        if not any_alive:
            self._acquisition_threads.clear()
        return any_alive

    def get_remaining_image_count(self) -> int:
        """Return total number of images in all camera buffers."""
        with self._lock:
            return sum(len(buf) for buf in self._seq_buffers.values())

    def pop_next_image(self) -> tuple | None:
        """Pop the next image from any camera buffer (round-robin).

        Returns
        -------
        tuple[np.ndarray, Mapping] | None
            Image and metadata, or None if all buffers are empty.
        """
        with self._lock:
            if not self._labels:
                return None

            # True round-robin: start from the camera after the last one we popped
            n = len(self._labels)
            for i in range(n):
                idx = (self._last_popped_idx + i + 1) % n
                label = self._labels[idx]
                buf = self._seq_buffers[label]
                if data := buf.pop_next():
                    self._last_popped_idx = idx
                    return data
            return None
