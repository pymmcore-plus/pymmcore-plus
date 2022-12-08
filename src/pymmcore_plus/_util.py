from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Literal, overload

import appdirs

from ._logger import logger

__all__ = ["find_micromanager", "_qt_app_is_running"]

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
