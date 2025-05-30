from __future__ import annotations

import threading
from collections.abc import Iterator, MutableMapping
from typing import TYPE_CHECKING, Any, cast

from pymmcore_plus.core import Keyword
from pymmcore_plus.core import Keyword as KW
from pymmcore_plus.core._mmcore_plus import CMMCorePlus
from pymmcore_plus.experimental.unicore._device_manager import PyDeviceManager

if TYPE_CHECKING:
    from typing import NewType

    from pymmcore import DeviceLabel

    PyDeviceLabel = NewType("PyDeviceLabel", DeviceLabel)


CURRENT = {
    KW.CoreCamera: None,
    KW.CoreShutter: None,
    KW.CoreFocus: None,
    KW.CoreXYStage: None,
    KW.CoreAutoFocus: None,
    KW.CoreSLM: None,
    KW.CoreGalvo: None,
}


class PropertyStateCache(MutableMapping[tuple[str, str], Any]):
    """A thread-safe cache for property states.

    Keys are tuples of (device_label, property_name), and values are the last known
    value of that property.
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], Any] = {}
        self._lock = threading.Lock()

    def __getitem__(self, key: tuple[str, str]) -> Any:
        with self._lock:
            try:
                return self._store[key]
            except KeyError:  # pragma: no cover
                prop, dev = key
                raise KeyError(
                    f"Property {prop!r} of device {dev!r} not found in cache"
                ) from None

    def __setitem__(self, key: tuple[str, str], value: Any) -> None:
        with self._lock:
            self._store[key] = value

    def __delitem__(self, key: tuple[str, str]) -> None:
        with self._lock:
            del self._store[key]

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._store

    def __iter__(self) -> Iterator[tuple[str, str]]:
        with self._lock:
            return iter(self._store.copy())  # Prevent modifications during iteration

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def __repr__(self) -> str:
        with self._lock:
            return f"{self.__class__.__name__}({self._store!r})"


class _CoreDevice:
    """A virtual core device.

    This mirrors the pattern used in CMMCore, where there is a virtual "core" device
    that maintains state about various "current" (real) devices.  When a call is made to
    `setSomeThing()` without specifying a device label, the CoreDevice is used to
    determine which real device to use.
    """

    def __init__(self, state_cache: PropertyStateCache) -> None:
        self._state_cache = state_cache
        self._pycurrent: dict[Keyword, PyDeviceLabel | None] = {}
        self.reset_current()

    def reset_current(self) -> None:
        self._pycurrent.update(CURRENT)

    def current(self, keyword: Keyword) -> PyDeviceLabel | None:
        return self._pycurrent[keyword]

    def set_current(self, keyword: Keyword, label: str | None) -> None:
        self._pycurrent[keyword] = cast("PyDeviceLabel", label)
        self._state_cache[(KW.CoreDevice, keyword)] = label


class UniCoreBase(CMMCorePlus):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pydevices = PyDeviceManager()  # manager for python devices
        self._state_cache = PropertyStateCache()  # threadsafe cache for property states
        self._pycore = _CoreDevice(self._state_cache)  # virtual core for python

    def _set_current_if_pydevice(self, keyword: Keyword, label: str) -> str:
        """Helper function to set the current core device if it is a python device.

        If the label is a python device, the current device is set and the label is
        cleared (in preparation for calling `super().setDevice()`), otherwise the
        label is returned unchanged.
        """
        if label in self._pydevices:
            self._pycore.set_current(keyword, label)
            label = ""
        elif not label:
            self._pycore.set_current(keyword, None)
        return label
