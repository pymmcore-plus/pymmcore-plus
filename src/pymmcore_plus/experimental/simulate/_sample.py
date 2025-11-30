"""Sample simulation that integrates with CMMCorePlus."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from typing import TYPE_CHECKING
from unittest.mock import patch

from ._render import RenderConfig, RenderEngine

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator, Sequence
    from typing import Any

    import numpy as np

    from pymmcore_plus import CMMCorePlus
    from pymmcore_plus.metadata.schema import SummaryMetaV1

    from ._objects import SampleObject


class Sample:
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
    """

    def __init__(
        self,
        objects: Sequence[SampleObject],
        config: RenderConfig | None = None,
    ) -> None:
        self._objects = list(objects)
        self._config = config or RenderConfig()
        self._engine = RenderEngine(self._objects, self._config)

    # ------------- Object Management -------------

    @property
    def objects(self) -> list[SampleObject]:
        """List of sample objects."""
        return self._objects

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

    # ------------- Rendering -------------

    def render(self, state: SummaryMetaV1) -> np.ndarray:
        """Render the sample directly without patching.

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
        return self._engine.render(state)

    def __repr__(self) -> str:
        return f"Sample({len(self._objects)} objects, config={self._config!r})"

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
