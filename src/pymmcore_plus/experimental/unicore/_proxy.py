"""Proxy objects expose a subset of an object's API.

Useful, e.g., for passing a core-like object to python-side device adapters without
exposing the entirety of the core.
"""

from __future__ import annotations

import types
from itertools import chain
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast, get_type_hints

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pymmcore_plus.core._mmcore_plus import CMMCorePlus

T = TypeVar("T")


class PSignalInstance(Protocol):
    """A signal instance that can only emit."""

    def emit(self, *args: Any) -> Any:
        """Emits the signal with the given arguments."""


class CoreEventsProxy(Protocol):
    """Signals that Device Adapters can emit directly."""

    propertyChanged: PSignalInstance  # (str, str, str)
    stagePositionChanged: PSignalInstance  # (str, float)
    XYStagePositionChanged: PSignalInstance  # (str, float, float)
    exposureChanged: PSignalInstance  # (str, float)
    SLMExposureChanged: PSignalInstance  # (str, float)
    # channelGroupChanged: PSignalInstance  # (str)
    # configGroupChanged: PSignalInstance  # (str, str)
    # configSet: PSignalInstance  # (str, str)


class CMMCoreProxy(Protocol):
    """Exposed CMMCcorePlus attributes that devices may access."""

    @property
    def events(self) -> CoreEventsProxy:
        """Events that devices may emit."""


def create_core_proxy(core: CMMCorePlus) -> CMMCoreProxy:
    """Create a proxy object for CMMCorePlus that only exposes CMMCoreProxy."""
    return create_proxy(core, CMMCoreProxy, {"events": CoreEventsProxy})


# ---------------------------------------------------------


class _ImmutableModule(types.ModuleType):
    __frozen__ = False

    def __setattr__(self, name: str, value: Any) -> None:
        if self.__frozen__:
            raise AttributeError(  # pragma: no cover
                f"Attributes on proxy {self.__name__!r} cannot be modified."
            )
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        raise AttributeError(  # pragma: no cover
            f"Attributes on proxy {self.__name__!r} cannot be modified."
        )


def create_proxy(
    obj: Any, protocol: type[T], sub_proxies: Mapping[str, type] | None = None
) -> T:
    """Create a proxy object that implements the given protocol.

    Parameters
    ----------
    obj : Any
        The object to proxy.
    protocol : type[T]
        The protocol template to implement.  The names and annotations of the protocol
        define the attributes that will be exposed on the proxy.
    sub_proxies : Mapping[str, type], optional
        A mapping of attribute names to sub-protocols.  If an attribute is in this
        mapping, it will be proxied with the corresponding sub-protocol. For example,
        if `sub_proxies={"foo": FooProtocol}`, then `proxy.foo` will be a proxy object
        that implements `FooProtocol`.

    Examples
    --------
    ```python
    class MyProtocol(Protocol):
        def foo(self) -> None: ...


    class MyClass:
        def foo(self) -> None: ...
        def bar(self) -> None: ...


    proxy = create_proxy(MyClass(), MyProtocol)
    proxy.foo()  # OK
    proxy.bar()  # AttributeError
    ```
    """
    sub_proxies = sub_proxies or {}

    # Get all public attribute names from the protocol (both from dir() and type hints)
    allowed_names = {
        x
        for x in chain(dir(protocol), get_type_hints(protocol))
        if not x.startswith("_")  # Exclude private/dunder attributes
    }

    # Create an immutable module to act as our proxy object
    proxy = _ImmutableModule(protocol.__name__)

    # Iterate through each allowed attribute name
    for attr_name in allowed_names:
        # Get the actual attribute from the source object
        attr = getattr(obj, attr_name)

        # Check if this attribute should be sub-proxied
        if subprotocol := sub_proxies.get(attr_name):
            # Look for nested sub-proxies on attr_name, e.g. `attr_name.sub_attr`
            # Filter sub_proxies for keys that start with "attr_name."
            sub = {
                k.split(".", 1)[1]: v  # Remove the "attr_name." prefix
                for k, v in sub_proxies.items()
                if k.startswith(f"{attr_name}.")
            }
            # Recursively create a proxy for this attribute
            attr = create_proxy(attr, subprotocol, sub)

        # Set the attribute on our proxy object
        setattr(proxy, attr_name, attr)

    # Freeze the proxy to prevent further modifications
    proxy.__frozen__ = True

    # Return the proxy cast to the expected protocol type
    return cast("T", proxy)
