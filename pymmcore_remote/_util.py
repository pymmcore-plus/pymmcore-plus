import os
import sys
from pathlib import Path


def find_micromanager():
    """Locate a Micro-Manager folder (for device adapters)."""
    from loguru import logger

    # environment variable takes precedence
    env_path = os.getenv("MICROMANAGER_PATH")
    if env_path and os.path.isdir(env_path):
        logger.debug(f"using MM path from env var: {env_path}")
        return env_path
    # then look for an installation in this folder (use `install_mm.sh` to install)
    sfx = "_win" if os.name == "nt" else "_mac"
    local_install = list(Path(__file__).parent.glob(f"Micro-Manager*{sfx}"))
    if local_install:
        logger.debug(f"using MM path from env var: {local_install[0]}")
        return str(local_install[0])

    applications = {
        "darwin": Path("/Applications/"),
        "win32": Path("C:/Program Files/"),
    }
    try:
        return str(next(applications.get(sys.platform).glob("Micro-Manager*")))
    except KeyError:
        raise NotImplementedError(
            f"MM autodiscovery not implemented for platform: {sys.platform}"
        )
    except StopIteration:
        logger.error("could not find micromanager directory")
