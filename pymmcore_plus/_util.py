import os
import re
import sys
from itertools import chain
from pathlib import Path
from typing import Optional, Type

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


def wrap_for_pyro(cls: Type) -> Type:
    """Create proxy class compatible with pyro.

    Some classes, such as those autogenerated by SWIG, may be difficult
    to expose via `Pyro.api.expose`, because Pyro wants to add attributes
    directly to every class and class method that it exposes.  In some
    cases, this leads to an error like:

    AttributeError: 'method_descriptor' object has no attribute '_pyroExposed'

    This wrapper takes a class and returns a proxy class whose methods can
    all be modified.
    """

    def __init__(self, *args, **kwargs) -> None:
        self._obj = cls(*args, **kwargs)

    def _proxy_method(name):
        def _f(self, *args, **kwargs):
            obj = getattr(self, "_obj")
            method = getattr(obj, name)
            return method(*args, **kwargs)

        _f.__name__ = name
        return _f

    _dict_ = {}
    for k, v in chain(*(c.__dict__.items() for c in reversed(cls.mro()))):
        if callable(v) and not k.startswith("_"):
            _dict_[k] = _proxy_method(k)
            for attr in dir(v):
                if attr.startswith("_pyro"):
                    setattr(_dict_[k], attr, getattr(v, attr))

    _dict_["__init__"] = __init__
    return type(f"{cls.__name__}Proxy", (), _dict_)
