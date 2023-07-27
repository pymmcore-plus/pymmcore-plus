from __future__ import annotations

import importlib
import os
import sys
from functools import wraps
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING, Literal, overload

import appdirs

if TYPE_CHECKING:
    from typing import TYPE_CHECKING, Any, Callable, TypeVar

    from typing_extensions import ParamSpec

    P = ParamSpec("P")
    R = TypeVar("R")


__all__ = ["find_micromanager", "_qt_app_is_running", "retry"]

USER_DATA_DIR = Path(appdirs.user_data_dir(appname="pymmcore-plus"))
USER_DATA_MM_PATH = USER_DATA_DIR / "mm"
PYMMCORE_PLUS_PATH = Path(__file__).parent.parent


@overload
def find_micromanager(return_first: Literal[True] = True) -> str | None:
    ...


@overload
def find_micromanager(return_first: Literal[False]) -> list[str]:
    ...


def find_micromanager(return_first: bool = True) -> str | None | list[str]:
    r"""Locate a Micro-Manager folder (for device adapters).

    In order, this will look for:

    1. An environment variable named `MICROMANAGER_PATH`
    2. A `Micro-Manager*` folder in the `pymmcore-plus` user data directory
       (this is the default install location when running `mmcore install`)

        - **Windows**: C:\Users\\[user]\AppData\Local\pymmcore-plus\pymmcore-plus
        - **macOS**: ~/Library/Application Support/pymmcore-plus
        - **Linux**: ~/.local/share/pymmcore-plus

    3. A `Micro-Manager*` folder in the `pymmcore_plus` package directory (this is the
       default install location when running `python -m pymmcore_plus.install`)
    4. The default micro-manager install location:

        - **Windows**: `C:/Program Files/`
        - **macOS**: `/Applications`
        - **Linux**: `/usr/local/lib`

    !!! note

        This function is used by [`pymmcore_plus.CMMCorePlus`][] to locate the
        micro-manager device adapters.  By default, the output of this function
        is passed to
        [`setDeviceAdapterSearchPaths`][pymmcore_plus.CMMCorePlus.setDeviceAdapterSearchPaths]
        when creating a new `CMMCorePlus` instance.

    Parameters
    ----------
    return_first : bool, optional
        If True (default), return the first found path.  If False, return a list of
        all found paths.
    """
    from ._logger import logger

    # environment variable takes precedence
    full_list: list[str] = []
    env_path = os.getenv("MICROMANAGER_PATH")
    if env_path and os.path.isdir(env_path):
        if return_first:
            logger.debug(f"using MM path from env var: {env_path}")
            return env_path
        full_list.append(env_path)

    # then look in appdirs.user_data_dir
    user_install = sorted(USER_DATA_MM_PATH.glob("Micro-Manager*"), reverse=True)
    if user_install:
        if return_first:
            logger.debug(f"using MM path from user install: {user_install[0]}")
            return str(user_install[0])
        full_list.extend([str(x) for x in user_install])

    # then look for an installation in this folder (from `pymmcore_plus.install`)
    sfx = "_win" if os.name == "nt" else "_mac"
    local_install = list(PYMMCORE_PLUS_PATH.glob(f"**/Micro-Manager*{sfx}"))
    if local_install:
        if return_first:
            logger.debug(f"using MM path from local install: {local_install[0]}")
            return str(local_install[0])
        full_list.extend([str(x) for x in local_install])

    applications = {
        "darwin": Path("/Applications/"),
        "win32": Path("C:/Program Files/"),
        "linux": Path("/usr/local/lib"),
    }
    if sys.platform not in applications:
        raise NotImplementedError(
            f"MM autodiscovery not implemented for platform: {sys.platform}"
        )
    app_path = applications[sys.platform]
    pth = next(app_path.glob("[m,M]icro-[m,M]anager*"), None)
    if return_first:
        if pth is None:
            logger.error(f"could not find micromanager directory in {app_path}")
            return None
        logger.debug(f"using MM path found in applications: {pth}")
        return str(pth)
    if pth is not None:
        full_list.append(str(pth))
    return full_list


def _qt_app_is_running() -> bool:
    for modname in {"PyQt5", "PySide2", "PyQt6", "PySide6"}:
        if modname in sys.modules:
            QtWidgets = importlib.import_module(".QtWidgets", modname)
            return QtWidgets.QApplication.instance() is not None
    return False


@overload
def retry(
    func: Literal[None] | None = ...,
    tries: int = ...,
    exceptions: type[BaseException] | tuple[type[BaseException], ...] = ...,
    delay: float | None = ...,
    logger: Callable[[str], Any] | None = ...,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    ...


@overload
def retry(
    func: Callable[P, R],
    tries: int = ...,
    exceptions: type[BaseException] | tuple[type[BaseException], ...] = ...,
    delay: float | None = ...,
    logger: Callable[[str], Any] | None = ...,
) -> Callable[P, R]:
    ...


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

    dashs = ["-" * w for w in col_widths]
    print(fmt.format(*dashs))

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
    rows = list(zip(*data.values()))
    if sort is not None:
        try:
            sort_idx = [x.lower() for x in data].index(sort.lower())
        except ValueError:
            raise ValueError(
                f"invalid sort column: {sort!r}. Must be one of {list(data)}"
            ) from None
        rows.sort(key=lambda x: x[sort_idx])
    return rows
