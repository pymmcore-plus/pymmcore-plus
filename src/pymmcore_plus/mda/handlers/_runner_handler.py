"""Handler for writing MDA sequences using the ome-writers library."""

from __future__ import annotations

import atexit
import os
import queue
import shutil
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import ome_writers as omew
from ome_writers._schema import DimensionList, DTypeStr  # noqa: TC002

from pymmcore_plus._logger import logger

if TYPE_CHECKING:
    from collections.abc import Iterator

    import numpy as np
    import useq
    from typing_extensions import Self

    from pymmcore_plus.metadata import FrameMetaV1, SummaryMetaV1


class StreamSettings(omew.AcquisitionSettings):
    """Acquisition settings for MDA output.

    Subclass of `ome_writers.AcquisitionSettings` with `dimensions`, `dtype`,
    and `plate` made optional, since they can be derived from the MDASequence
    and metadata at runtime.

    Parameters
    ----------
    asynchronous : bool, optional
        If True, frames are enqueued and written in a background thread,
        decoupling I/O from the MDA loop. Default is True.
    queue_maxsize : int, optional
        Maximum number of frames to hold in the write queue when
        `asynchronous` is True. Default is 100.
    """

    dimensions: DimensionList | None = None
    dtype: DTypeStr | None = None
    plate: omew.Plate | None = None
    asynchronous: bool = True
    queue_maxsize: int = 100

    def model_post_init(self, __context: object) -> None:
        """Eagerly import the backend module after model creation.

        Modules like tifffile register threading atexit handlers on import.
        When run_mda starts a background thread, the main thread may exit and
        begin interpreter shutdown before the lazy import occurs on the worker
        thread, causing ``RuntimeError: can't register atexit after shutdown``
        on Python 3.12+.  Importing the backend here (on the main thread at
        settings-creation time) prevents that race.
        """
        super().model_post_init(__context)
        from ome_writers._stream import AVAILABLE_BACKENDS

        fmt = self.format
        backend_name: str = getattr(fmt, "backend", "auto")
        if backend_name == "auto":
            target = getattr(fmt, "name", None)
            for meta in AVAILABLE_BACKENDS.values():
                if meta.format == target:
                    __import__(meta.module_path)
                    break
        elif backend_name in AVAILABLE_BACKENDS:
            __import__(AVAILABLE_BACKENDS[backend_name].module_path)

    def _validate_storage_order(self) -> StreamSettings:
        if self.dimensions is None:
            return self
        return super()._validate_storage_order()  # type: ignore[no-any-return]

    def _validate_plate_positions(self) -> StreamSettings:
        if self.dimensions is None:
            return self
        return super()._validate_plate_positions()  # type: ignore[no-any-return]

    def _warn_chunk_buffer_memory(self) -> StreamSettings:
        if self.dimensions is None:
            return self
        return super()._warn_chunk_buffer_memory()  # type: ignore[no-any-return]


def _register_cleanup_atexit(path: str) -> None:
    """Register atexit handler to cleanup directory."""

    @atexit.register
    def _cleanup(_path: str = path) -> None:  # pragma: no cover
        if os.path.isdir(_path):
            shutil.rmtree(_path, ignore_errors=True)


_STOP = object()


class OMERunnerHandler:
    """MDA handler that writes to OME-ZARR or OME-TIFF using ome-writers library.

    Parameters
    ----------
    stream_settings : StreamSettings
        Settings describing the output format, path, and async/queue behavior.

    Notes
    -----
    To customize write behavior, override `write_frame`. It is called in both
    sync and async modes — in async mode it runs on the background writer thread.
    """

    def __init__(self, stream_settings: StreamSettings) -> None:
        if not stream_settings.root_path:
            raise ValueError(
                "`path` is always required unless you are using"
                "OMERunnerHandler.in_tempdir() which auto-generates a temporary"
                "directory and `path` can be empty."
            )

        self._stream_settings = stream_settings
        self._stream: omew.OMEStream | None = None

        # for asynchronous writing
        self._asynchronous = stream_settings.asynchronous
        self._queue: queue.Queue = queue.Queue(maxsize=stream_settings.queue_maxsize)
        self._writer_thread: threading.Thread | None = None
        self._write_error: BaseException | None = None

    @property
    def stream(self) -> omew.OMEStream | None:
        """The OMEStream object used for writing frames."""
        return self._stream

    @property
    def stream_settings(self) -> StreamSettings:
        """The StreamSettings used to create the stream."""
        return self._stream_settings

    @property
    def queue(self) -> queue.Queue[tuple[object, ...] | object]:
        """The queue used for asynchronous writing.

        Accessible for advanced subclass customization (e.g., monitoring
        queue depth or replacing with a custom queue type).
        """
        return self._queue

    @classmethod
    def in_tempdir(cls, stream_settings: StreamSettings) -> Self:
        """Create an OMERunnerHandler with a temporary directory as the stream path."""
        temp_dir = tempfile.mkdtemp(prefix="pymmcp_ome_runner_")
        _register_cleanup_atexit(temp_dir)
        stream_settings = StreamSettings(
            root_path=str(Path(temp_dir) / (stream_settings.root_path or "pymmcp")),
            format=stream_settings.format,
            overwrite=stream_settings.overwrite,
        )
        return cls(stream_settings)

    def prepare(self, sequence: useq.MDASequence, meta: SummaryMetaV1 | None) -> None:
        """Prepare the settings to create the stream."""
        self._stream = None

        if meta is None:
            raise ValueError("meta is required for OMERunnerHandler")

        image_infos = meta.get("image_infos")
        if not image_infos:
            raise ValueError(
                "Metadata must contain 'image_infos' to determine image properties."
            )
        image_info = image_infos[0]
        width = image_info.get("width")
        height = image_info.get("height")
        pixel_size = image_info.get("pixel_size_um")  # optional

        if width is None or height is None:
            raise ValueError(
                "Metadata 'image_infos' must contain 'width' and 'height' keys."
            )

        dtype = self._stream_settings.dtype or image_info.get("dtype")
        if dtype is None:
            raise ValueError(
                "Data type could not be determined. Please specify `dtype` in "
                "StreamSettings or include 'dtype' in metadata 'image_infos'."
            )

        dims = self._stream_settings.dimensions
        plate = self._stream_settings.plate
        if dims is None or plate is None:
            useq_settings = omew.useq_to_acquisition_settings(
                sequence,
                image_width=width,
                image_height=height,
                pixel_size_um=pixel_size,
            )
            if dims is None:
                dims = tuple(useq_settings.get("dimensions", ()))
            if plate is None:
                plate = useq_settings.get("plate")

        acq_settings = omew.AcquisitionSettings(
            root_path=str(self._stream_settings.root_path),
            format=self._stream_settings.format,
            dtype=dtype,
            overwrite=self._stream_settings.overwrite,
            dimensions=dims,
            plate=plate,
        )
        self._stream = omew.create_stream(settings=acq_settings)
        self._write_error = None

        if self._asynchronous:
            self._writer_thread = threading.Thread(
                target=self._drain_queue, daemon=True
            )
            self._writer_thread.start()

    def write_frame(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: FrameMetaV1
    ) -> None:
        """Write a single frame to the stream.

        Override this method to customize write behavior. It is called in both
        synchronous and asynchronous modes — in async mode it runs on the
        background writer thread, so implementations must be safe for that
        context.
        """
        self._stream.append(frame)  # type: ignore

    def cleanup(self) -> None:
        """Close the stream when sequence finishes."""
        if self._writer_thread is not None:
            remaining = self._queue.qsize()
            if remaining:
                logger.info(
                    "Waiting for %d remaining frames to be written...",
                    remaining,
                )
            self._queue.put(_STOP)
            self._writer_thread.join()
            self._writer_thread = None

        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def _writeframe(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: FrameMetaV1
    ) -> None:
        """Write frame to the stream.

        Delegates to `write_frame` directly (sync) or via the background queue
        (async). Subclass and override `write_frame` to customize write behavior.
        """
        if self._write_error is not None:
            raise RuntimeError("Background writer failed") from self._write_error

        if self._asynchronous:
            self._enqueue_frame(frame, event, meta)
        else:
            self.write_frame(frame, event, meta)

    def _enqueue_frame(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: FrameMetaV1
    ) -> None:
        """Enqueue frame for background writing."""
        try:
            self._queue.put((frame, event, meta), timeout=5)
        except queue.Full:
            logger.warning(
                "Write queue full — MDA thread blocked waiting for writer to catch up."
            )
            self._queue.put((frame, event, meta))

    def _drain_queue(self) -> None:
        """Background thread: consume frames from queue and call write_frame."""
        if self._stream is None:
            return

        while True:
            item = self._queue.get()
            if item is _STOP:
                break
            frame, event, meta = item
            try:
                self.write_frame(frame, event, meta)
            except Exception as e:
                self._write_error = e
                break


class OMERunnerHandlerGroup:
    """Container that manages multiple OMERunnerHandler instances.

    Delegates `prepare`, `_writeframe`, and `cleanup` calls to all handlers.
    """

    def __init__(self, handlers: list[OMERunnerHandler] | None = None) -> None:
        self._handlers: list[OMERunnerHandler] = handlers or []

    def __iter__(self) -> Iterator[OMERunnerHandler]:
        return iter(self._handlers)

    def __len__(self) -> int:
        return len(self._handlers)

    def __bool__(self) -> bool:
        return bool(self._handlers)

    def get_handlers(self) -> list[OMERunnerHandler]:
        """Get the list of handlers in the group."""
        return self._handlers

    def prepare(self, sequence: useq.MDASequence, meta: SummaryMetaV1 | None) -> None:
        """Prepare all handlers for the acquisition."""
        for handler in self._handlers:
            handler.prepare(sequence, meta)

    def writeframe(
        self, frame: np.ndarray, event: useq.MDAEvent, meta: FrameMetaV1
    ) -> None:
        """Write a frame to all handlers."""
        for handler in self._handlers:
            handler._writeframe(frame, event, meta)  # noqa: SLF001

    def cleanup(self) -> None:
        """Close all handlers and clear the group."""
        for handler in self._handlers:
            handler.cleanup()
        self._handlers.clear()
