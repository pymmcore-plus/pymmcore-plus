from __future__ import annotations

import datetime
import importlib
import importlib.metadata
import os
import platform
import sys
import warnings
from collections import defaultdict
from contextlib import contextmanager, suppress
from functools import wraps
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING, cast, overload

from platformdirs import user_data_dir

from . import _discovery

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from typing import Any, Literal, TypeVar

    QtConnectionType = Literal["AutoConnection", "DirectConnection", "QueuedConnection"]

    from typing import ParamSpec, TypeGuard

    from .core.events._protocol import PSignalInstance

    P = ParamSpec("P")
    R = TypeVar("R")

try:
    # if we have wurlitzer, use it to suppress MMCorePlus output
    # during device discovery
    from wurlitzer import pipes as no_stdout
except ImportError:
    from contextlib import nullcontext as no_stdout


__all__ = ["no_stdout", "retry", "signals_backend"]

APP_NAME = "pymmcore-plus"
USER_DATA_DIR = Path(user_data_dir(appname=APP_NAME))
USER_DATA_MM_PATH = USER_DATA_DIR / "mm"
CURRENT_MM_PATH = USER_DATA_MM_PATH / ".current_mm"
PYMMCORE_PLUS_PATH = Path(__file__).parent.parent
PYMM_SIGNALS_BACKEND = "PYMM_SIGNALS_BACKEND"


def _imported_qt_modules() -> Iterator[str]:
    for modname in {"PyQt5", "PySide2", "PyQt6", "PySide6"}:
        if modname in sys.modules:
            yield modname


def _qt_app_is_running() -> bool:
    for modname in _imported_qt_modules():
        try:
            # in broken environments modname can be a namespace package...
            # and QtWidgets will still be unavailable
            QtWidgets = importlib.import_module(".QtWidgets", modname)
        except ImportError:  # pragma: no cover
            continue
        return QtWidgets.QApplication.instance() is not None
    return False  # pragma: no cover


def signals_backend() -> Literal["qt", "psygnal"]:
    """Return the name of the event backend to use."""
    env_var = os.environ.get(PYMM_SIGNALS_BACKEND, "auto").lower()
    if env_var not in {"qt", "psygnal", "auto"}:
        warnings.warn(
            f"{PYMM_SIGNALS_BACKEND} must be one of ['qt', 'psygnal', 'auto']. "
            f"not: {env_var!r}. Using 'auto'.",
            stacklevel=1,
        )
        env_var = "auto"

    qt_app_running = _qt_app_is_running()
    if env_var == "auto":
        return "qt" if qt_app_running else "psygnal"
    if env_var == "qt":
        if qt_app_running or list(_imported_qt_modules()):
            return "qt"
        warnings.warn(
            f"{PYMM_SIGNALS_BACKEND} set to 'qt', but no Qt app is running. "
            "Falling back to 'psygnal'.",
            stacklevel=1,
        )
    return "psygnal"


@overload
def retry(
    func: Literal[None] | None = ...,
    tries: int = ...,
    exceptions: type[BaseException] | tuple[type[BaseException], ...] = ...,
    delay: float | None = ...,
    logger: Callable[[str], Any] | None = ...,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...
@overload
def retry(
    func: Callable[P, R],
    tries: int = ...,
    exceptions: type[BaseException] | tuple[type[BaseException], ...] = ...,
    delay: float | None = ...,
    logger: Callable[[str], Any] | None = ...,
) -> Callable[P, R]: ...
def retry(
    func: Callable[P, R] | None = None,
    tries: int = 3,
    exceptions: type[BaseException] | tuple[type[BaseException], ...] = Exception,
    delay: float | None = None,
    logger: Callable[[str], Any] | None = None,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Retry a function `tries` times, with an exponential backoff.

    Parameters
    ----------
    func : Callable
        The function to retry.
    exceptions : Union[Type[Exception], tuple[Type[Exception], ...]]
        The exception or exceptions to catch and retry on. defaults to `Exception`.
    tries : int
        The maximum number of times to retry the function. Defaults to 3.
    delay : float
        The delay between retries, in seconds. Defaults to `None`.
    logger : Callable[[str], Any] | None
        The logger to use for logging retry attempts.  If `None`, no logging
        will be performed. Defaults to `None`.

    Returns
    -------
    Callable
        A function that will retry `func` until it either succeeds, or
        `tries` attempts have been made.


    Examples
    --------
    ```python
    from pymmcore_plus import CMMCorePlus
    from pymmcore_plus._util import retry

    mmc = CMMCorePlus()
    mmc.loadSystemConfiguration()


    @retry(exceptions=RuntimeError, delay=0.5, logger=print)
    def snap_image():
        return mmc.snap()


    snap_image()
    ```
    """

    def deco(_func: Callable[P, R]) -> Callable[P, R]:
        @wraps(_func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            _tries = tries
            while _tries > 1:
                try:
                    return _func(*args, **kwargs)
                except exceptions as e:
                    _tries -= 1
                    if logger is not None:
                        logger(
                            f"{type(e).__name__} {e} caught, trying {_tries} more times"
                        )
                    if delay:
                        sleep(delay)
            return _func(*args, **kwargs)

        return wrapper

    return deco(func) if func is not None else deco


def print_tabular_data(data: dict[str, list[str]], sort: str | None = None) -> None:
    """Print tabular data in a human-readable format.

    Parameters
    ----------
    data : dict[str, list[str]]
        A dictionary of column names and lists of values.
    sort : str | None
        Optionally sort the table by the given column name.
    """
    try:
        _rich_print_table(data, sort=sort)
        return
    except ImportError:
        from ._logger import logger

        logger.warning("`pip install rich` for a nicer table display")

    col_widths = [len(x) for x in data]
    for i, col in enumerate(data.values()):
        for val in col:
            col_widths[i] = max(col_widths[i], len(str(val)))
    fmt = " | ".join(f"{{:<{w}s}}" for w in col_widths)

    print(fmt.format(*data.keys()))

    dashes = ["-" * w for w in col_widths]
    print(fmt.format(*dashes))

    for row in _sorted_rows(data, sort=sort):
        print(fmt.format(*(str(x) for x in row)))


def _rich_print_table(data: dict[str, list[str]], sort: str | None = None) -> None:
    """Print pretty table with rich."""
    from rich.console import Console
    from rich.table import Table

    if "Type" in data:
        type_emojis = {
            "Hub": ":electric_plug: ",
            "Camera": ":camera: ",
            "Shutter": ":light_bulb: ",
            "State": ":green_circle: ",
            "Stage": ":up_arrow:  ",
            "XYStage": ":joystick:  ",
            "Core": ":blue_heart: ",
            "AutoFocus": ":wavy_dash: ",
        }
        data["Type"] = [type_emojis.get(x, "") + x for x in data["Type"]]

    console = Console()
    table = Table()
    for i, header in enumerate(data):
        if header == "Current":
            style = "bold"
        else:
            style = "" if i else "bold green"
        table.add_column(header, style=style)

    for row in _sorted_rows(data, sort=sort):
        table.add_row(*row)

    console.print(table)


def _sorted_rows(data: dict, sort: str | None) -> list[tuple]:
    """Return a list of rows, sorted by the given column name."""
    rows = list(zip(*data.values(), strict=False))
    if sort is not None:
        with suppress(ValueError):
            # silently ignore if the sort column is not found
            sort_idx = [x.lower() for x in data].index(sort.lower())
            rows.sort(key=lambda x: x[sort_idx])
    return rows


@contextmanager
def listeners_connected(
    emitter: Any,
    *listeners: Any,
    name_map: dict[str, str] | None = None,
    qt_connection_type: QtConnectionType | None = None,
) -> Iterator[None]:
    """Context manager for listening to signals.

    This provides a way for one or more `listener` to temporarily connect to signals on
    an `emitter`. Any method names on `listener` that match signal names on `emitter`
    will be connected, then disconnected when the context exits (see example below).
    Names can be mapped explicitly using `name_map` if the signal names do not match
    exactly.

    Parameters
    ----------
    emitter : Any
        An object that has signals (e.g. `psygnal.SignalInstance` or
        `QtCore.SignalInstance`).  Basically, anything with `connect` and `disconnect`
        methods.
    listeners : Any
        Object(s) that has methods matching the name of signals on `emitter`.
    name_map : dict[str, str] | None
        Optionally map signal names on `emitter` to different method names on
        `listener`.  This can be used to connect callbacks with different names. By
        default, callbacks names must match the signal names exactly.
    qt_connection_type: str | None
        ADVANCED: Optionally specify the Qt connection type to use when connecting
        signals, in the case where `emitter` is a Qt object.  This is useful for
        connecting to Qt signals in a thread-safe way. Must be one of
        `"AutoConnection"`, `"DirectConnection"`, `"QueuedConnection"`.
        If `None` (the default), `Qt.ConnectionType.AutoConnection` will be used.

    Examples
    --------
    ```python
    from qtpy.QtCore import Signal

    # OR
    from psygnal import Signal


    class Emitter:
        signalName = Signal(int)


    class Listener:
        def signalName(self, value: int):
            print(value)


    emitter = Emitter()
    listener = Listener()

    with listeners_connected(emitter, listener):
        emitter.signalName.emit(42)  # prints 42
    ```
    """
    # mapping of signal name on emitter to a set of tokens to disconnect later.
    tokens: defaultdict[str, set[Any]] = defaultdict(set)
    name_map = name_map or {}

    for listener in listeners:
        if isinstance(listener, dict):  # pragma: no cover
            import warnings

            warnings.warn(
                "Received a dict as a listener. Did you mean to use `name_map`?",
                stacklevel=2,
            )
            continue

        # get a list of common names:
        listener_names = set(dir(listener)).union(name_map)
        common_names: set[str] = set(dir(emitter)).intersection(listener_names)

        for attr_name in common_names:
            if attr_name.startswith("__"):
                continue
            if _is_signal_instance(signal := getattr(emitter, attr_name)):
                slot_name = name_map.get(attr_name, attr_name)
                if callable(slot := getattr(listener, slot_name)):
                    if qt_connection_type and _is_qt_signal(signal):
                        from qtpy.QtCore import Qt

                        ctype = getattr(Qt.ConnectionType, qt_connection_type)
                        token = signal.connect(slot, ctype)  # type: ignore
                    else:
                        token = signal.connect(slot)

                    # This only seems to happen on PySide2
                    if token is None or isinstance(token, bool):
                        token = slot
                    tokens[attr_name].add(token)

    try:
        yield
    finally:
        for attr_name, token_set in tokens.items():
            for token in token_set:
                sig = cast("PSignalInstance", getattr(emitter, attr_name))
                sig.disconnect(token)


def _is_signal_instance(obj: Any) -> TypeGuard[PSignalInstance]:
    # minimal protocol shared by psygnal and Qt that we need here.
    return (
        hasattr(obj, "connect") and callable(obj.connect) and hasattr(obj, "disconnect")
    )


def _is_qt_signal(obj: Any) -> TypeGuard[PSignalInstance]:
    modname = getattr(type(obj), "__module__", "")
    return "Qt" in modname or "Shiboken" in modname


def system_info() -> dict[str, str]:
    """Return a dictionary of system information.

    This backs the `mmcore info` command in the CLI.
    """
    import pymmcore_plus

    info = {
        "python": sys.version,
        "platform": platform.platform(),
        "pymmcore-plus": getattr(pymmcore_plus, "__version__", "err"),
    }
    try:
        import pymmcore

        info["pymmcore"] = getattr(pymmcore, "__version__", "err")
    except ImportError:
        info["pymmcore"] = ""
    try:
        import pymmcore_nano

        info["pymmcore-nano"] = getattr(pymmcore_nano, "__version__", "err")
    except ImportError:
        info["pymmcore-nano"] = ""

    with suppress(Exception):
        core = pymmcore_plus.CMMCorePlus.instance()
        info["core-version-info"] = core.getVersionInfo()
        info["api-version-info"] = core.getAPIVersionInfo()

    if (mm_path := _discovery.find_micromanager()) is not None:
        path = str(Path(mm_path).resolve())
        path = path.replace(os.path.expanduser("~"), "~")  # privacy
        info["adapter-path"] = path
    else:
        info["adapter-path"] = "not found"

    for pkg in (
        "useq-schema",
        "pymmcore-widgets",
        "napari-micromanager",
        "napari",
        "tifffile",
        "zarr",
    ):
        with suppress(ImportError, PackageNotFoundError):
            info[pkg] = importlib.metadata.version(pkg)

            if pkg == "pymmcore-widgets":
                with suppress(ImportError, AttributeError):
                    import qtpy

                    info["qt"] = f"{qtpy.API_NAME} {qtpy.QT_VERSION}"

    return info


if sys.version_info < (3, 11):

    def _utcnow() -> datetime.datetime:
        return datetime.datetime.utcnow()
else:

    def _utcnow() -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


def timestamp() -> str:
    """Return the current timestamp, try using local timezone, in ISO format.

    YYYY-MM-DD HH:MM:SS.mmmmmm+HH:MM
    """
    now = _utcnow()
    with suppress(Exception):
        now = now.astimezone()
    return now.isoformat()
