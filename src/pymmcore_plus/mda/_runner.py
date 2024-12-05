from __future__ import annotations

from collections.abc import Iterable, Sequence
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import TYPE_CHECKING, Any

from useq.experimental import MDARunner as _MDARunner

from pymmcore_plus._logger import logger

from ._thread_relay import mda_listeners_connected
from .events import _get_auto_MDA_callback_class

if TYPE_CHECKING:
    from typing import TypeAlias

    from useq import MDAEvent

    from ._engine import MDAEngine

    SingleOutput: TypeAlias = Path | str | object


class MDARunner(_MDARunner):
    """Object that executes a multi-dimensional experiment using an MDAEngine.

    This object is available at [`CMMCorePlus.mda`][pymmcore_plus.CMMCorePlus.mda].

    This is the main object that runs a multi-dimensional experiment; it does so by
    driving an acquisition engine that implements the
    useq.experimental.protocolsPMDAEngine`][pymmcore_plus.mda.PMDAEngine] protocol.
    It emits signals at specific
    times during the experiment (see
    [`PMDASignaler`][pymmcore_plus.mda.events.PMDASignaler] for details on the signals
    that are available to connect to and when they are emitted).
    """

    if TYPE_CHECKING:
        # NOTE:
        # this return annotation is a lie, since the user can set it to their own engine
        # but in MOST cases, this is the engine that will be used by default, so it's
        # convenient for IDEs to point to this rather than the abstract protocol.
        engine: MDAEngine | None

    def __init__(self) -> None:
        signals = _get_auto_MDA_callback_class()()
        super().__init__(signal_emitter=signals, logger=logger)

    def run(
        self,
        events: Iterable[MDAEvent],
        *,
        output: SingleOutput | Sequence[SingleOutput] | None = None,
    ) -> None:
        """Run the multi-dimensional acquisition defined by `sequence`.

        Most users should not use this directly as it will block further
        execution. Instead, use the
        [`CMMCorePlus.run_mda`][pymmcore_plus.CMMCorePlus.run_mda] method which will
        run on a thread.

        Parameters
        ----------
        events : Iterable[MDAEvent]
            An iterable of `useq.MDAEvents` objects to execute.
        output : SingleOutput | Sequence[SingleOutput] | None, optional
            The output handler(s) to use.  If None, no output will be saved.
            The value may be either a single output or a sequence of outputs,
            where a "single output" can be any of the following:

            - A string or Path to a directory to save images to. A handler will be
                created automatically based on the extension of the path.
                - `.zarr` files will be handled by `OMEZarrWriter`
                - `.ome.tiff` files will be handled by `OMETiffWriter`
                - A directory with no extension will be handled by `ImageSequenceWriter`
            - A handler object that implements the `DataHandler` protocol, currently
                meaning it has a `frameReady` method.  See `mda_listeners_connected`
                for more details.
        """
        with self._outputs_connected(output):
            super().run(events)

    def _outputs_connected(
        self, output: SingleOutput | Sequence[SingleOutput] | None
    ) -> AbstractContextManager:
        """Context in which output handlers are connected to the frameReady signal."""
        if output is None:
            return nullcontext()

        if isinstance(output, (str, Path)) or not isinstance(output, Sequence):
            output = [output]

        # convert all items to handler objects
        handlers: list[Any] = []
        for item in output:
            if isinstance(item, (str, Path)):
                handlers.append(self._handler_for_path(item))
            else:
                # TODO: better check for valid handler protocol
                # quick hack for now.
                if not hasattr(item, "frameReady"):
                    raise TypeError(
                        "Output handlers must have a frameReady method. "
                        f"Got {item} with type {type(item)}."
                    )
                handlers.append(item)

        return mda_listeners_connected(*handlers, mda_events=self._signals)

    def _handler_for_path(self, path: str | Path) -> object:
        """Convert a string or Path into a handler object.

        This method picks from the built-in handlers based on the extension of the path.
        """
        path = str(Path(path).expanduser().resolve())
        if path.endswith(".zarr"):
            from pymmcore_plus.mda.handlers import OMEZarrWriter

            return OMEZarrWriter(path)

        if path.endswith((".tiff", ".tif")):
            from pymmcore_plus.mda.handlers import OMETiffWriter

            return OMETiffWriter(path)

        # FIXME: ugly hack for the moment to represent a non-existent directory
        # there are many features that ImageSequenceWriter supports, and it's unclear
        # how to infer them all from a single string.
        if not (Path(path).suffix or Path(path).exists()):
            from pymmcore_plus.mda.handlers import ImageSequenceWriter

            return ImageSequenceWriter(path)

        raise ValueError(f"Could not infer a writer handler for path: '{path}'")
