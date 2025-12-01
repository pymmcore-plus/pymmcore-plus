"""Sample simulation that integrates with CMMCorePlus."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from typing import TYPE_CHECKING
from unittest.mock import patch

from ._render import RenderConfig, RenderEngine

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Iterator
    from typing import Any

    import numpy as np

    from pymmcore_plus import CMMCorePlus
    from pymmcore_plus.metadata.schema import SummaryMetaV1

    from ._objects import SampleObject


class Sample:
    """A simulated microscope sample that integrates with CMMCorePlus.

    Use `sample.patch(core)` as a context manager to intercept image acquisition
    calls and return rendered images based on microscope state.

    Parameters
    ----------
    objects : Iterable[SampleObject]
        Sample objects to render (points, lines, shapes, etc.).
    config : RenderConfig | None
        Rendering configuration. If None, uses default config.
    """

    def __init__(
        self, objects: Iterable[SampleObject], config: RenderConfig | None = None
    ) -> None:
        self._engine = RenderEngine(list(objects), config or RenderConfig())

    # ------------- Object Management -------------

    @property
    def objects(self) -> list[SampleObject]:
        """List of sample objects."""
        return self._engine.objects

    @property
    def config(self) -> RenderConfig:
        """Rendering configuration."""
        return self._engine.config

    # ------------- Rendering -------------

    def render(self, state: SummaryMetaV1) -> np.ndarray:
        """Render the sample for the given microscope state."""
        return self._engine.render(state)

    def __repr__(self) -> str:
        return f"Sample({len(self.objects)} objects, config={self.config!r})"

    # ------------- Patching -------------

    @contextmanager
    def patch(self, core: CMMCorePlus) -> Generator[Sample, None, None]:
        """Patch the core to use this sample for image generation.

        Parameters
        ----------
        core : CMMCorePlus
            The core instance to patch.

        Yields
        ------
        Sample
            This sample instance.
        """
        patcher = CoreSamplePatcher(core, self)
        with patch_with_object(core, patcher):
            yield self


class CoreSamplePatcher:
    def __init__(self, core: CMMCorePlus, sample: Sample) -> None:
        self._core = core
        self._sample = sample
        self._snapped_state: SummaryMetaV1 | None = None
        self._original_snapImage = core.snapImage

    def snapImage(self) -> None:
        """Capture state before calling original snapImage."""
        self._snapped_state = self._core.state()
        self._original_snapImage()  # emit signals, etc.

    def getImage(self, *_: Any, **__: Any) -> np.ndarray:
        if not self._snapped_state:
            raise RuntimeError(
                "No snapped state available. Call snapImage() before getImage()."
            )
        return self._sample.render(self._snapped_state)

    def getLastImage(self, *_: Any, **__: Any) -> np.ndarray:
        """Return rendered image based on current state (for live mode)."""
        return self._sample.render(self._core.state())


@contextmanager
def patch_with_object(target: Any, patch_object: Any) -> Iterator[Any]:
    """
    Patch methods on target object with methods from patch_object.

    Parameters
    ----------
    target : Any
        object to be patched
    patch_object : Any
        object containing replacement methods

    Examples
    --------
    ```
    class MyClass:
        def foo(self):
            return "original"

        def bar(self):
            return "original"


    class Patch:
        def foo(self):
            return "patched"


    obj = MyClass()
    with patch_with_object(obj, Patch()):
        assert obj.foo() == "patched"
        assert obj.bar() == "original"
    ```
    """
    with ExitStack() as stack:
        # Get all methods from patch_object
        patch_methods = {
            name: getattr(patch_object, name)
            for name in dir(patch_object)
            if (not name.startswith("_") and callable(getattr(patch_object, name)))
        }

        # Patch each method that exists on target (if spec=True)
        for method_name, method in patch_methods.items():
            if hasattr(target, method_name):
                # Use patch.object to do the actual patching
                stack.enter_context(patch.object(target, method_name, method))

        yield target
