from __future__ import annotations

from contextlib import AbstractContextManager, ContextDecorator
from functools import wraps
from types import TracebackType
from typing import TYPE_CHECKING, Any, Callable, Generic, Iterator, TypeVar, overload
from unittest.mock import patch

if TYPE_CHECKING:
    from unittest.mock import _patch

    import numpy as np
    from pymmcore import CMMCore
    from typing_extensions import Literal, ParamSpec

    P = ParamSpec("P")
    
R = TypeVar("R")


class _CorePatcher(AbstractContextManager, ContextDecorator, Generic[R]):
    """Context manager that patches the provided (or global) mmcore object."""

    def __init__(
        self,
        func: Callable[P, Iterator[R]],
        args: tuple[Any, ...],
        kwds: dict[str, Any],
        loop: bool = True,
        mmcore: CMMCore | None = None,
    ) -> None:
        from pymmcore_plus import CMMCorePlus

        self._core = mmcore or CMMCorePlus.instance()
        self._loop = loop

        self.func, self.args, self.kwds = func, args, kwds
        self.gen = self._make_new_generator()

        self._patchers: list[_patch] = []
        for attr in dir(self):
            if hasattr(self._core, attr):
                patcher = patch.object(self._core, attr, getattr(self, attr))
                self._patchers.append(patcher)

        # ensure context manager instances have good docstrings
        doc = getattr(func, "__doc__", None)
        if doc is None:
            doc = type(self).__doc__
        self.__doc__ = doc

    def _make_new_generator(self) -> Iterator[R]:
        return self.func(*self.args, **self.kwds)

    def _recreate_cm(self) -> _MockSampleContextManager:
        # This overrides the ContextDecorator._recreate_cm method.
        # _MockSampleContextManager instances are one-shot context managers, so the
        # context manager must be recreated each time a decorated function is
        # called
        return self.__class__(self.func, self.args, self.kwds)

    def start(self) -> None:
        """Start all patchers."""
        for patcher in self._patchers:
            patcher.start()

    def stop(self) -> None:
        """Stop all patchers."""
        for patcher in self._patchers:
            patcher.stop()

    def __enter__(self) -> None:
        # do not keep args and kwds alive unnecessarily
        # they are only needed for recreation, which is not possible anymore
        del self.args, self.kwds, self.func
        self.start()

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.stop()


class _MockSampleContextManager(_CorePatcher['np.ndarray']):
    def snapImage(self, *args: Any, **kwargs: Any) -> None:
        # not currently used, but could be.
        ...

    def getImage(self, numChannel: int | None = None, **kwargs: Any) -> np.ndarray:
        try:
            return next(self.gen)
        except StopIteration:
            if self._loop:
                self.gen = self._make_new_generator()
                return next(self.gen)
            else:
                raise RuntimeError("generator didn't yield") from None


@overload
def mock_sample(
    func: Callable[P, Iterator[np.ndarray]]
) -> Callable[P, _MockSampleContextManager]:
    ...


@overload
def mock_sample(
    func: Literal[None] | None = None,
    *,
    loop: bool = ...,
    mmcore: CMMCore | None = ...,
) -> Callable[
    [Callable[P, Iterator[np.ndarray]]], Callable[P, _MockSampleContextManager]
]:
    ...


def mock_sample(
    func: Callable[P, Iterator[np.ndarray]] | None = None,
    *,
    loop: bool = True,
    mmcore: CMMCore | None = None,
) -> (
    Callable[P, _MockSampleContextManager]
    | Callable[
        [Callable[P, Iterator[np.ndarray]]], Callable[P, _MockSampleContextManager]
    ]
):
    """Decorator to create a context manager that mocks the core's getImage method.

    When the context is entered, [`core.getImage()`][pymmcore_plus.CMMCorePlus.getImage]
    is patched to return a new image from the decorated generator function each time
    it is called.

    !!! Note

        The patched `mmcore` object needn't be a `CMMCorePlus` instance. It can be
        a plain `pymmcore.CMMCore` object, (or *any* object with a `getImage`
        method).

    Parameters
    ----------
    func : Callable[..., Iterator[np.ndarray]]
        A function that yields numpy arrays.
    loop : bool, optional
        If `True` (the default), the decorated function will be called again when the
        generator is exhausted.
    mmcore : CMMCore, optional
        The [pymmcore.CMMCore][] instance to patch.  If `None` (default), the global
        [`CMMCorePlus.instance()`][pymmcore_plus.CMMCorePlus.instance] will be used.

    Returns
    -------
    Callable[..., _MockSampleContextManager]
        A context manager that patches `core.getImage()` to return a new image from the
        decorated generator function each time it is called.

    Examples
    --------
    ```python
    from pymmcore_plus import CMMCorePlus, mock_sample

    core = CMMCorePlus()

    @mock_sample(mmcore=core)
    def noisy_sample(shape):
        yield np.random.random(shape)

    with noisy_sample(shape=(10, 10)):
        core.snapImage()  # unnecessary, but harmless
        print(core.getImage().shape)  # (10, 10)
    ```
    """

    def _decorator(
        func: Callable[P, Iterator[np.ndarray]]
    ) -> Callable[P, _MockSampleContextManager]:
        @wraps(func)
        def helper(*args: Any, **kwds: Any) -> _MockSampleContextManager:
            return _MockSampleContextManager(func, args, kwds, loop=loop, mmcore=mmcore)

        return helper

    return _decorator(func) if func is not None else _decorator
