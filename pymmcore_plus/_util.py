import os
import re
import sys
from pathlib import Path
from typing import Optional

camel_to_snake = re.compile(r"(?<!^)(?=[A-Z])")


def find_micromanager() -> Optional[str]:
    """Locate a Micro-Manager folder (for device adapters).

    In order, this will look for:
    1. An environment variable named MICROMANAGER_PATH
    2. An installation in the pymmcore_plus package directory (this is the
       default install location when running python -m pymmcore_plus.install)
    3. The default micromanager install location:
        - `C:/Program Files/` on windows
        - `/Applications` on mac
        - `/usr/local/lib` on linux
    """
    from loguru import logger

    # environment variable takes precedence
    env_path = os.getenv("MICROMANAGER_PATH")
    if env_path and os.path.isdir(env_path):
        logger.debug(f"using MM path from env var: {env_path}")
        return env_path
    # then look for an installation in this folder (from `pymmcore_plus.install`)
    sfx = "_win" if os.name == "nt" else "_mac"
    local_install = list(Path(__file__).parent.parent.glob(f"**/Micro-Manager*{sfx}"))
    if local_install:
        logger.debug(f"using MM path from local install: {local_install[0]}")
        return str(local_install[0])

    applications = {
        "darwin": Path("/Applications/"),
        "win32": Path("C:/Program Files/"),
        "linux": Path("/usr/local/lib"),
    }
    try:
        app_path = applications[sys.platform]
        pth = str(next(app_path.glob("[m,M]icro-[m,M]anager*")))
        logger.debug(f"using MM path found in applications: {pth}")
        return pth
    except KeyError:
        raise NotImplementedError(
            f"MM autodiscovery not implemented for platform: {sys.platform}"
        )
    except StopIteration:
        logger.error(f"could not find micromanager directory in {app_path}")
        return None


def _qt_app_is_running() -> bool:
    for modname in {"PyQt5", "PySide2", "PyQt6", "PySide6"}:
        if qmodule := sys.modules.get(modname):
            QtWidgets = getattr(qmodule, "QtWidgets")
            return QtWidgets.QApplication.instance() is not None
    return False
