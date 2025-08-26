from __future__ import annotations

import ctypes
import os
import re
import sys
import warnings
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, overload

from platformdirs import user_data_dir

from . import _pymmcore

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Literal


__all__ = ["discover_mm", "find_micromanager", "use_micromanager"]

APP_NAME = "pymmcore-plus"
USER_DATA_DIR = Path(user_data_dir(appname=APP_NAME))
USER_DATA_MM_PATH = USER_DATA_DIR / "mm"
CURRENT_MM_PATH = USER_DATA_MM_PATH / ".current_mm"
PYMMCORE_PLUS_PATH = Path(__file__).parent.parent


PYMMCORE_DIV = _pymmcore.version_info.device_interface


@dataclass
class DiscoveredMM:
    """A discovered path with micro-manager devices."""

    path: Path
    env_var: str | None = None
    device_interface: int | None = None
    device_paths: set[Path] | None = field(default=None, repr=False)
    num_devices: int | None = None
    div_compatible: bool = False
    is_current: bool = False

    def __post_init__(self) -> None:
        # normalize early to avoid cache key duplication from symlinks or relative paths
        try:
            self.path = self.path.resolve()
        except Exception:
            # be defensive if resolution fails on odd platforms
            self.path = Path(self.path)

    def _populate_info(self, force: bool = False) -> None:
        # one time on-demand population of additional metadata
        if self.device_interface is None or force:
            self.device_interface = get_first_device_interface_version(self.path)
            self.div_compatible = self.device_interface == PYMMCORE_DIV
            self.num_devices = len(set(_iter_device_paths(self.path)))

    def merge_from(self, other: DiscoveredMM) -> None:
        # preserve flags from whichever source had them
        if other.is_current:
            self.is_current = True
        if other.env_var and not self.env_var:
            self.env_var = other.env_var
        if other.device_interface and not self.device_interface:
            self.device_interface = other.device_interface
            self.div_compatible = other.div_compatible
            self.num_devices = other.num_devices


def _env_var_mm() -> Iterator[DiscoveredMM]:
    """Discover Micro-Manager installations from the MICROMANAGER_PATH env var."""
    env_path = os.getenv("MICROMANAGER_PATH")
    if env_path and os.path.isdir(env_path):
        yield DiscoveredMM(path=Path(env_path), env_var="MICROMANAGER_PATH")


def _current_mm() -> Iterator[DiscoveredMM]:
    """Discover Micro-Manager installation at the CURRENT_MM_PATH file."""
    if CURRENT_MM_PATH.exists():
        path = Path(CURRENT_MM_PATH.read_text().strip())
        if path.is_dir():
            yield DiscoveredMM(path=path, is_current=True)
        else:
            from ._logger import logger

            logger.warning(
                f"User-selected micromanager path {path} is not a directory, clearing."
            )
            CURRENT_MM_PATH.unlink(missing_ok=True)


def _mmcore_installed_mm(glob: str = "Micro-Manager*") -> Iterator[DiscoveredMM]:
    """Discover Micro-Manager installations in the pymmcore-plus user data directory."""
    for path in sorted(USER_DATA_MM_PATH.glob(glob), reverse=True):
        if path.is_dir():
            yield DiscoveredMM(path=path)


def _mm_test_adapter_mm() -> Iterator[DiscoveredMM]:
    """Discover Micro-Manager from the mm-test-adapters package."""
    with suppress(ImportError, AttributeError):
        import mm_test_adapters

        path = Path(mm_test_adapters.device_adapter_path())
        if path.is_dir():
            yield DiscoveredMM(path=path)


def _application_installs() -> Iterator[DiscoveredMM]:
    """Discover official Micro-Manager installations in the application directory."""
    applications = {
        "darwin": Path("/Applications/"),
        "win32": Path("C:/Program Files/"),
        "linux": Path("/usr/local/lib"),
    }
    if app_path := applications.get(sys.platform):
        for pth in app_path.glob("[m,M]icro-[m,M]anager*"):
            yield DiscoveredMM(path=pth)


def _iter_mm_paths() -> Iterator[DiscoveredMM]:
    """Iterate over all discovered Micro-Manager paths.

    Order here influences the return value of find_micromanager() when
    `return_first` is True.
    """
    yield from _env_var_mm()
    yield from _current_mm()
    yield from _mmcore_installed_mm()
    yield from _mm_test_adapter_mm()
    yield from _application_installs()


_DISCOVERED_MMS: dict[Path, DiscoveredMM] = {}


def discover_mm() -> Iterator[DiscoveredMM]:
    """Discover Micro-Manager installations with caching and dedup by path."""
    yielded: set[Path] = set()

    for candidate in _iter_mm_paths():
        key = candidate.path
        existing = _DISCOVERED_MMS.get(key)

        if existing is None:
            candidate._populate_info()  # noqa: SLF001
            # only cache and consider entries that look like real installs
            # If the discovery came from an explicit environment variable, keep
            # the entry even if it doesn't currently contain device adapter
            # libraries. This allows users (and tests) to point to a path that
            # may be populated later or is intentionally empty.
            if candidate.device_interface is None and candidate.env_var is None:
                continue
            _DISCOVERED_MMS[key] = existing = candidate
        else:
            # enrich cached entry with flags learned from other discovery sources
            existing.merge_from(candidate)

        if key not in yielded:  # never double yield
            yielded.add(key)
            yield existing


@overload
def find_micromanager(return_first: Literal[True] = ...) -> str | None: ...
@overload
def find_micromanager(return_first: Literal[False]) -> list[str]: ...
def find_micromanager(return_first: bool = True) -> str | None | list[str]:
    r"""Locate a Micro-Manager folder (for device adapters).

    In order, this will look for:

    1. An environment variable named `MICROMANAGER_PATH`
    2. A path stored in the `CURRENT_MM_PATH` file (set by `use_micromanager`).
    3. A `Micro-Manager*` folder in the `pymmcore-plus` user data directory
       (this is the default install location when running `mmcore install`)

        - **Windows**: C:\Users\\[user]\AppData\Local\pymmcore-plus\pymmcore-plus
        - **macOS**: ~/Library/Application Support/pymmcore-plus
        - **Linux**: ~/.local/share/pymmcore-plus

    4. A `Micro-Manager*` folder in the `pymmcore_plus` package directory (this is the
       default install location when running `python -m pymmcore_plus.install`)
    5. The default micro-manager install location:

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

    for discovered_mm in discover_mm():
        if return_first:
            # If the path was explicitly provided via the MICROMANAGER_PATH
            # environment variable, prefer it even if it doesn't currently
            # contain device adapter libraries. This allows users (and tests)
            # to point to a path that will be used as-is.
            if discovered_mm.env_var is not None:
                logger.debug(
                    "Using Micro-Manager path from %s: %s",
                    discovered_mm.env_var,
                    discovered_mm.path,
                )
                return str(discovered_mm.path)

            if discovered_mm.div_compatible:
                logger.debug(
                    "Using Micro-Manager path: %s (device interface %s)",
                    discovered_mm.path,
                    discovered_mm.device_interface,
                )
                return str(discovered_mm.path)
            elif discovered_mm.is_current:
                warnings.warn(
                    f"The current user-selected version of Micro-Manager at "
                    f"{discovered_mm.path} has an incompatible device interface "
                    f"({discovered_mm.device_interface}). The installed version "
                    f"of pymmcore requires: {PYMMCORE_DIV}). Clearing.",
                    stacklevel=2,
                )
                CURRENT_MM_PATH.unlink(missing_ok=True)
                object.__setattr__(discovered_mm, "is_current", False)

    if return_first:
        # if we got here it means no compatible version was found

        others = "\n".join(
            [str(d.path) for d in _DISCOVERED_MMS.values() if not d.div_compatible]
        )

        logger.error(
            f"Could not find a compatible Micro-Manager installation for the "
            f"device interface required by pymmcore {PYMMCORE_DIV}.\n\n"
            f"Discovered installations:\n"
            f"{others}\n"
            f"Please run 'mmcore install'."
        )
        return None

    return [str(d.path) for d in _DISCOVERED_MMS.values()]


def _match_mm_pattern(pattern: str | re.Pattern[str]) -> Path | None:
    """Locate an existing Micro-Manager folder using a regex pattern."""
    for _path in find_micromanager(return_first=False):
        if not isinstance(pattern, re.Pattern):
            pattern = str(pattern)
        if re.search(pattern, _path) is not None:
            return Path(_path)
    return None


def use_micromanager(
    path: str | Path | None = None, pattern: str | re.Pattern[str] | None = None
) -> Path | None:
    """Set the preferred Micro-Manager path.

    This sets the preferred micromanager path, and persists across sessions.
    This path takes precedence over everything *except* the `MICROMANAGER_PATH`
    environment variable.

    Parameters
    ----------
    path : str | Path | None
        Path to an existing directory. This directory should contain micro-manager
        device adapters. If `None`, the path will be determined using `pattern`.
    pattern : str Pattern | | None
        A regex pattern to match against the micromanager paths found by
        `find_micromanager`. If no match is found, a `FileNotFoundError` will be raised.
    """
    if path is None:
        if pattern is None:  # pragma: no cover
            raise ValueError("One of 'path' or 'pattern' must be provided")
        if (path := _match_mm_pattern(pattern)) is None:
            options = "\n".join(find_micromanager(return_first=False))
            raise FileNotFoundError(
                f"No micromanager path found matching: {pattern!r}. Options:\n{options}"
            )

    if not isinstance(path, Path):  # pragma: no cover
        path = Path(path)

    path = path.expanduser().resolve()
    if not path.is_dir():  # pragma: no cover
        if not path.exists():
            raise FileNotFoundError(f"Path not found: {path!r}")
        raise NotADirectoryError(f"Not a directory: {path!r}")

    USER_DATA_MM_PATH.mkdir(parents=True, exist_ok=True)
    CURRENT_MM_PATH.write_text(str(path))
    return path


def _iter_device_paths(folder: Path) -> Iterator[Path]:
    """Iterate over device shared library paths in `folder`."""
    valid_extensions = {".dll", ".so.0", ""}
    for lib_path in folder.glob("*mmgr_dal*"):
        if lib_path.suffix in valid_extensions:
            yield lib_path


def get_first_device_interface_version(folder: Path | str) -> int | None:
    for dev_path in _iter_device_paths(Path(folder)):
        try:
            return get_device_interface_version(dev_path)
        except Exception:
            continue
    return None


def get_device_interface_version(lib_path: str | Path) -> int:
    """Return the device interface version from the given library path."""
    if sys.platform.startswith("win"):
        lib = ctypes.WinDLL(str(lib_path))
    else:
        lib = ctypes.CDLL(str(lib_path))

    try:
        func = lib.GetDeviceInterfaceVersion
    except AttributeError:
        raise RuntimeError(
            f"Function 'GetDeviceInterfaceVersion' not found in {lib_path}"
        ) from None

    func.restype = ctypes.c_long
    func.argtypes = []
    return func()  # type: ignore[no-any-return]
