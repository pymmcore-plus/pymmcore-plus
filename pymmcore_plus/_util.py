import os
import re
import sys
from pathlib import Path
from typing import Optional

camel_to_snake = re.compile(r"(?<!^)(?=[A-Z])")


def find_micromanager() -> Optional[str]:
    """Locate a Micro-Manager folder (for device adapters)."""
    from loguru import logger

    # environment variable takes precedence
    env_path = os.getenv("MICROMANAGER_PATH")
    if env_path and os.path.isdir(env_path):
        logger.debug(f"using MM path from env var: {env_path}")
        return env_path
    # then look for an installation in this folder (use `install_mm.sh` to install)
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
