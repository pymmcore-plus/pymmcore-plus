"""Sample simulation that integrates with CMMCorePlus."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, overload
from unittest.mock import patch

from ._render import RenderConfig, RenderEngine

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType
    from unittest.mock import _patch

    import numpy as np

    from pymmcore_plus import CMMCorePlus
    from pymmcore_plus.metadata.schema import SummaryMetaV1

    from ._objects import SampleObject


class Sample(AbstractContextManager["Sample"]):
    """A simulated microscope sample that integrates with CMMCorePlus.

    This class allows you to define a virtual sample with drawable objects
    (points, lines, shapes, etc.) and have them rendered as if they were
    real sample features when acquiring images through CMMCorePlus.

    When installed on a core, this sample intercepts `snapImage()` and
    `getImage()` calls to return rendered images based on the current
    microscope state (stage position, exposure, pixel size, etc.).

    Parameters
    ----------
    objects : Sequence[SampleObject]
        List of sample objects to render.
    config : RenderConfig | None
        Rendering configuration. If None, uses default config.

    Examples
    --------
    Basic usage as context manager:

    >>> from pymmcore_plus import CMMCorePlus
    >>> from pymmcore_plus.experimental.simulate import Sample, Point, Line
    >>>
    >>> core = CMMCorePlus.instance()
    >>> core.loadSystemConfiguration()
    >>>
    >>> sample = Sample(
    ...     [
    ...         Point(0, 0, intensity=200, radius=5),
    ...         Line((0, 0), (100, 100), intensity=100),
    ...     ]
    ... )
    >>>
    >>> with sample.patch(core):
    ...     core.snapImage()
    ...     img = core.getImage()  # Returns rendered simulation!

    Manual install/uninstall:

    >>> sample.install(core)
    >>> # ... acquire images ...
    >>> sample.uninstall()

    Accessing the underlying engine:

    >>> sample.engine.config.noise_std = 5.0  # Modify config
    """

    def __init__(
        self,
        objects: Sequence[SampleObject],
        config: RenderConfig | None = None,
    ) -> None:
        self._objects = list(objects)
        self._config = config or RenderConfig()
        self._engine = RenderEngine(self._objects, self._config)

        # State for patching
        self._core: CMMCorePlus | None = None
        self._patchers: list[_patch[None]] = []
        self._snapped_state: SummaryMetaV1 | None = None
        self._installed = False

    @property
    def objects(self) -> list[SampleObject]:
        """List of sample objects."""
        return self._objects

    @property
    def config(self) -> RenderConfig:
        """Rendering configuration."""
        return self._config

    @property
    def engine(self) -> RenderEngine:
        """The underlying render engine."""
        return self._engine

    @property
    def is_installed(self) -> bool:
        """Whether the sample is currently installed on a core."""
        return self._installed

    def add_object(self, obj: SampleObject) -> None:
        """Add a sample object.

        Parameters
        ----------
        obj : SampleObject
            Object to add.
        """
        self._objects.append(obj)

    def remove_object(self, obj: SampleObject) -> None:
        """Remove a sample object.

        Parameters
        ----------
        obj : SampleObject
            Object to remove.
        """
        self._objects.remove(obj)

    def clear_objects(self) -> None:
        """Remove all sample objects."""
        self._objects.clear()

    def patch(self, core: CMMCorePlus) -> Sample:
        """Return a context manager that patches the core.

        Parameters
        ----------
        core : CMMCorePlus
            The core instance to patch.

        Returns
        -------
        Sample
            Self, for use as context manager.

        Examples
        --------
        >>> with sample.patch(core):
        ...     core.snapImage()
        ...     img = core.getImage()
        """
        self._core = core
        return self

    def install(self, core: CMMCorePlus) -> None:
        """Install the sample on a core (patch snapImage/getImage).

        Parameters
        ----------
        core : CMMCorePlus
            The core instance to patch.

        Raises
        ------
        RuntimeError
            If already installed on a core.
        """
        if self._installed:
            raise RuntimeError("Sample is already installed. Call uninstall() first.")

        self._core = core
        self._setup_patchers()
        self._start_patchers()
        self._installed = True

    def uninstall(self) -> None:
        """Uninstall the sample (restore original methods).

        Raises
        ------
        RuntimeError
            If not currently installed.
        """
        if not self._installed:
            raise RuntimeError("Sample is not installed.")

        self._stop_patchers()
        self._core = None
        self._installed = False

    def _setup_patchers(self) -> None:
        """Create patchers for core methods."""
        if self._core is None:
            raise RuntimeError("No core set. Call patch() or install() first.")

        self._patchers = [
            patch.object(self._core, "snapImage", self._snapImage),  # type: ignore[arg-type]
            patch.object(self._core, "getImage", self._getImage),  # type: ignore[arg-type]
        ]

    def _start_patchers(self) -> None:
        """Start all patchers."""
        for patcher in self._patchers:
            patcher.start()

    def _stop_patchers(self) -> None:
        """Stop all patchers."""
        for patcher in self._patchers:
            patcher.stop()
        self._patchers.clear()

    def _snapImage(self) -> None:
        """Patched snapImage that captures state for rendering."""
        if self._core is None:
            raise RuntimeError("No core available.")
        # Capture current state for use in getImage
        self._snapped_state = self._core.state()

    @overload
    def _getImage(self) -> np.ndarray: ...
    @overload
    def _getImage(self, *, fix: bool = True) -> np.ndarray: ...
    @overload
    def _getImage(self, numChannel: int) -> np.ndarray: ...
    @overload
    def _getImage(self, numChannel: int, *, fix: bool = True) -> np.ndarray: ...

    def _getImage(
        self, numChannel: int | None = None, *, fix: bool = True
    ) -> np.ndarray:
        """Patched getImage that returns rendered simulation."""
        if self._snapped_state is None:
            # No snap yet - get current state
            if self._core is None:
                raise RuntimeError("No core available.")
            self._snapped_state = self._core.state()

        # Render the image
        return self._engine.render(self._snapped_state)

    def __enter__(self) -> Sample:
        """Enter context manager - install the sample."""
        if self._core is None:
            raise RuntimeError(
                "No core set. Use `with sample.patch(core):` instead of `with sample:`"
            )
        self.install(self._core)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit context manager - uninstall the sample."""
        self.uninstall()

    def render(self, state: SummaryMetaV1 | None = None) -> np.ndarray:
        """Render the sample directly without patching.

        This is useful for testing or manual rendering.

        Parameters
        ----------
        state : SummaryMetaV1 | None
            Microscope state to render. If None and a core is set,
            uses current state from the core.

        Returns
        -------
        np.ndarray
            Rendered image.
        """
        if state is None:
            if self._core is None:
                raise ValueError(
                    "No state provided and no core set. "
                    "Either provide state or call patch(core) first."
                )
            state = self._core.state()
        return self._engine.render(state)

    def __repr__(self) -> str:
        status = "installed" if self._installed else "not installed"
        return (
            f"Sample({len(self._objects)} objects, {status}, config={self._config!r})"
        )
