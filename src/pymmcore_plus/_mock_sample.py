from __future__ import annotations

from contextlib import AbstractContextManager, ContextDecorator
from functools import wraps
from types import TracebackType
from typing import TYPE_CHECKING, Any, Callable, Iterator, overload
from unittest.mock import patch


if TYPE_CHECKING:
    import numpy as np
    from pymmcore import CMMCore
    from typing_extensions import Literal, ParamSpec

    _P = ParamSpec("_P")


class _MockSampleContextManager(AbstractContextManager, ContextDecorator):
    def __init__(
        self,
        image_generator: Callable[_P, Iterator[np.ndarray]],
        args: tuple[Any, ...],
        kwds: dict[str, Any],
        loop: bool = False,
        mmcore: CMMCore | None = None,
    ) -> None:
        from pymmcore_plus import CMMCorePlus

        self._mmcore = mmcore or CMMCorePlus.instance()
        self._loop = loop
        self._image_generator = image_generator

        self.gen = image_generator(*args, **kwds)
        self.func, self.args, self.kwds = image_generator, args, kwds
        self._patcher = patch.object(self._mmcore, "getImage", self._getImage)

        # ensure context manager instances have good docstrings
        doc = getattr(image_generator, "__doc__", None)
        if doc is None:
            doc = type(self).__doc__
        self.__doc__ = doc

    def _getImage(self, numChannel: int | None = None, **kwargs: Any) -> np.ndarray:
        try:
            return next(self.gen)
        except StopIteration:
            if self._loop:
                self.gen = self._image_generator()
                return next(self.gen)
            else:
                raise RuntimeError("generator didn't yield") from None

    def _recreate_cm(self) -> _MockSampleContextManager:
        # _GCMB instances are one-shot context managers, so the
        # CM must be recreated each time a decorated function is
        # called
        return self.__class__(self.func, self.args, self.kwds)

    def __enter__(self) -> None:
        # do not keep args and kwds alive unnecessarily
        # they are only needed for recreation, which is not possible anymore
        del self.args, self.kwds, self.func
        self._patcher.start()
        return None

    def __exit__(
        self,
        __exc_type: type[BaseException] | None,
        __exc_value: BaseException | None,
        __traceback: TracebackType | None,
    ) -> bool | None:
        self._patcher.stop()
        return None


@overload
def mock_sample(
    func: Callable[_P, Iterator[np.ndarray]]
) -> Callable[_P, _MockSampleContextManager]:
    ...


@overload
def mock_sample(
    func: Literal[None] = None,
    *,
    loop: bool = ...,
    mmcore: CMMCore | None = ...,
) -> Callable[
    [Callable[_P, Iterator[np.ndarray]]], Callable[_P, _MockSampleContextManager]
]:
    ...


def mock_sample(
    func: Callable[_P, Iterator[np.ndarray]] | None = None,
    *,
    loop: bool = False,
    mmcore: CMMCore | None = None,
) -> Callable[_P, _MockSampleContextManager] | Callable[
    [Callable[_P, Iterator[np.ndarray]]], Callable[_P, _MockSampleContextManager]
]:
    def _decorator(
        func: Callable[_P, Iterator[np.ndarray]]
    ) -> Callable[_P, _MockSampleContextManager]:
        @wraps(func)
        def helper(*args: Any, **kwds: Any) -> _MockSampleContextManager:
            return _MockSampleContextManager(func, args, kwds, loop=loop, mmcore=mmcore)

        return helper

    return _decorator(func) if func is not None else _decorator
