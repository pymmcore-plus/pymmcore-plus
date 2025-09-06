from __future__ import annotations

import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import zipfile
from contextlib import contextmanager, nullcontext
from functools import cache
from pathlib import Path
from platform import machine, system
from typing import TYPE_CHECKING, Callable, Protocol
from urllib.request import urlopen, urlretrieve

import typer

from pymmcore_plus import _pymmcore
from pymmcore_plus._util import USER_DATA_MM_PATH

if TYPE_CHECKING:
    from collections.abc import Iterator
    from contextlib import AbstractContextManager

    class _MsgLogger(Protocol):
        def __call__(self, text: str, color: str = "", emoji: str = "") -> None: ...


try:
    from rich import print as rich_print
    from rich import progress

    def _pretty_print(text: str, color: str = "", emoji: str = "") -> None:
        if emoji and not emoji.endswith(" "):
            emoji += " "
        if color and not color.startswith("["):
            color = f"[{color}]"
        rich_print(f"{emoji}{color}{text}")

    @contextmanager
    def _spinner(text: str, color: str = "bold blue") -> Iterator[None]:
        with progress.Progress(
            progress.SpinnerColumn(), progress.TextColumn(f"[{color}]{text}")
        ) as pbar:
            pbar.add_task(description=text, total=None)
            yield None

except ImportError:  # pragma: no cover
    progress = None  # type: ignore

    def _pretty_print(text: str, color: str = "", emoji: str = "") -> None:
        print(text)

    @contextmanager
    def _spinner(text: str, color: str = "") -> Iterator[None]:
        print(text)
        yield


PLATFORM = system()
MACH = machine()
BASE_URL = "https://download.micro-manager.org"
plat = {"Darwin": "Mac", "Windows": "Windows", "Linux": "Linux"}.get(PLATFORM)
DOWNLOADS_URL = f"{BASE_URL}/nightly/2.0/{plat}/"
TEST_ADAPTERS_REPO = "micro-manager/mm-test-adapters"
PYMMCORE_DIV = _pymmcore.version_info.device_interface

# Dates of release for each interface version.
# generally running `mmcore install -r <some_date>` will bring in devices with
# the NEW interface, introduced that day.
INTERFACES: dict[int, str] = {
    74: "20250815",
    73: "20250318",
    72: "20250318",
    71: "20221031",
    70: "20210219",
    69: "20180712",
    68: "20171107",
    67: "20160609",
    66: "20160608",
    65: "20150528",
    64: "20150515",
    63: "20150505",
    62: "20150501",
    61: "20140801",
    60: "20140618",
    59: "20140515",
    58: "20140514",
    57: "20140125",
    56: "20140120",
}


def _get_download_name(url: str) -> str:
    """Return the name of the file to be downloaded from `url`."""
    with urlopen(url) as tmp:
        content: str = tmp.headers.get("Content-Disposition")
        for part in content.split(";"):
            if "filename=" in part:
                return part.split("=")[1].strip('"')
    return ""


def _get_spinner(log_msg: _MsgLogger) -> Callable[[str], AbstractContextManager]:
    if log_msg is _pretty_print:
        spinner = _spinner
    else:

        @contextmanager
        def spinner(text: str, color: str = "") -> Iterator[None]:
            log_msg(text)
            yield

    return spinner


def _win_install(exe: Path, dest: Path, log_msg: _MsgLogger) -> None:
    spinner = _get_spinner(log_msg)
    cmd = [str(exe), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={dest}"]
    with spinner("Installing ..."):
        subprocess.run(cmd, check=True)


def _mac_install(dmg: Path, dest: Path, log_msg: _MsgLogger) -> None:
    """Install Micro-Manager `dmg` to `dest`."""
    # with progress bar, mount dmg
    spinner = _get_spinner(log_msg)
    with spinner(f"Mounting {dmg.name} ..."):
        proc = subprocess.run(
            ["hdiutil", "attach", "-nobrowse", str(dmg)],
            capture_output=True,
        )
        if proc.returncode != 0:  # pragma: no cover
            log_msg(
                f"\nError mounting {dmg.name}:\n{proc.stderr.decode()}",
                "bold red",
            )
            sys.exit(1)

    # get mount point
    disk_id, *_, volume = proc.stdout.splitlines()[-1].decode().split("\t")

    try:
        # with progress bar, mount dmg
        with spinner(f"Installing to {str(dest)!r} ..."):
            try:
                src = next(Path(volume).glob("Micro-Manager*"))
            except StopIteration:  # pragma: no cover
                log_msg(
                    "\nError: Could not find Micro-Manager in dmg.\n"
                    "Please report this at https://github.com/pymmcore-plus/"
                    "pymmcore-plus/issues/new",
                    "bold red",
                )
                sys.exit(1)
            install_path = dest / src.name
            shutil.copytree(src, install_path, dirs_exist_ok=True)
    finally:
        subprocess.run(
            ["hdiutil", "detach", disk_id.strip()], check=True, capture_output=True
        )

    log_msg("Fixing macOS permissions ...", "bold blue")
    # fix gatekeeper ... may require password?  But better if sudo not needed.
    cmd = ["xattr", "-r", "-d", "com.apple.quarantine", str(install_path)]
    subprocess.run(cmd)

    # # fix path randomization by temporarily copying elsewhere and back
    with tempfile.TemporaryDirectory() as tmpdir:
        _tmp = Path(tmpdir)
        os.rename(install_path / "ImageJ.app", _tmp / "ImageJ.app")
        os.rename(_tmp / "ImageJ.app", install_path / "ImageJ.app")


@cache
def available_versions() -> dict[str, str]:
    """Return a map of version -> url available for download.

    Returns a dict like:
    {
        '20220906': 'https://download.micro-manager.org/nightly/2.0/Mac/Micro-Manager-2.0.1-20220906.dmg',
        '20220901': 'https://download.micro-manager.org/nightly/2.0/Mac/Micro-Manager-2.0.1-20220901.dmg',
        '20220823': 'https://download.micro-manager.org/nightly/2.0/Mac/Micro-Manager-2.0.1-20220823.dmg',
    }
    """
    with urlopen(DOWNLOADS_URL) as resp:
        html = resp.read().decode("utf-8")

    all_links = re.findall(r'href="([^"]+)"', html)
    delim = "_" if PLATFORM == "Windows" else "-"
    return {
        ref.rsplit(delim, 1)[-1].split(".")[0]: BASE_URL + ref
        for ref in all_links
        if ref != "/" and "32bit" not in ref
    }


@cache
def _available_test_adapter_releases() -> dict[str, str]:
    """Get available releases from GitHub mm-test-adapters repository.

    Returns a dict like:
    {
        '20250825': '74.20250825',
        ...
    }
    """
    github_api_url = f"https://api.github.com/repos/{TEST_ADAPTERS_REPO}/releases"

    with urlopen(github_api_url) as resp:
        releases = json.loads(resp.read().decode("utf-8"))

    release_map = {}
    for release in releases:
        tag_name = release["tag_name"]  # e.g., "74.20250825"
        if "." in tag_name:
            _, date_part = tag_name.split(".", 1)  # Extract YYYYMMDD part
            release_map[date_part] = tag_name

    return release_map


def _get_platform_arch_string() -> str:
    """Get platform and architecture string for GitHub releases."""
    if PLATFORM == "Darwin":
        arch = "ARM64" if MACH == "arm64" else "X64"
        return f"macOS-{arch}"
    elif PLATFORM == "Windows":
        return "Windows-X64"
    elif PLATFORM == "Linux":
        return "Linux-X64"
    else:  # pragma: no cover
        raise ValueError(f"Unsupported platform: {PLATFORM}")


def _test_dev_install(
    dest: Path | str = USER_DATA_MM_PATH,
    release: str = "latest",
) -> None:
    """Install just the test devices into dest.

    From https://github.com/micro-manager/mm-test-adapters/releases/latest
    (Releases on github are versioned as: DIV.YYYYMMDD)

    If release is `latest-compatible`, it will install the latest compatible version
    of the test devices for the current device interface version.

    Parameters
    ----------
    dest : Path | str, optional
        Where to install Micro-Manager, by default will install to a pymmcore-plus
        folder in the user's data directory: `appdirs.user_data_dir()`.
    release : str, optional
        Which release to install, by default "latest-compatible". Should be a date
        in the form YYYYMMDD, "latest" to install the latest nightly release, or
        "latest-compatible" to install the latest nightly release that is
        compatible with the device interface version of the current pymmcore version.
    """
    dest = Path(dest).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)

    # Get available GitHub releases
    if not (github_releases := _available_test_adapter_releases()):  # pragma: no cover
        raise ValueError("No test device releases found on GitHub")

    # Build download URL
    filename = f"mm-test-adapters-{_get_platform_arch_string()}.zip"
    base_url = f"https://github.com/{TEST_ADAPTERS_REPO}/releases"
    if release == "latest-compatible":
        # Find the latest release compatible with the current device interface
        # this is easier with test devices because their version starts with the DIV
        available = sorted(github_releases.values(), reverse=True)
        for version in available:
            if version.startswith(f"{PYMMCORE_DIV}."):
                # Found a compatible version
                download_url = f"{base_url}/download/{version}/{filename}"
                tag_name = version
                break
        else:  # pragma: no cover
            raise ValueError(
                f"No compatible releases found for device interface {PYMMCORE_DIV}.  "
                f"Found: {available}"
            )
    elif release == "latest":
        download_url = f"{base_url}/latest/download/{filename}"
        tag_name = sorted(github_releases.values(), reverse=True)[0]
    else:
        if release not in github_releases:
            _available = ", ".join(sorted(github_releases.keys(), reverse=True))
            raise ValueError(
                f"Release {release!r} not found. Available releases: {_available}"
            )
        tag_name = github_releases[release]
        download_url = f"{base_url}/download/{tag_name}/{filename}"

    _dest = dest / f"Micro-Manager-{tag_name}"
    with tempfile.TemporaryDirectory() as tmpdir:
        # Download the zip file
        zip_path = Path(tmpdir) / filename
        _download_url(
            url=download_url, output_path=zip_path, show_progress=progress is not None
        )

        # Extract the zip file
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(_dest)

        # On macOS, remove quarantine attribute
        if PLATFORM == "Darwin":
            cmd = ["xattr", "-r", "-d", "com.apple.quarantine", str(_dest)]
            subprocess.run(cmd, check=False)  # Don't fail if xattr fails


def _download_url(url: str, output_path: Path, show_progress: bool = True) -> None:
    """Download `url` to `output_path` with a nice progress bar."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    if show_progress and progress is not None:
        pbar = progress.Progress(
            progress.BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            progress.DownloadColumn(),
        )
        task_id = pbar.add_task("Download..", filename=output_path.name, start=False)

        def hook(count: float, block_size: float, total_size: float) -> None:
            pbar.update(task_id, total=int(total_size))
            pbar.start_task(task_id)
            pbar.update(task_id, advance=block_size)

    else:
        pbar = nullcontext()  # type: ignore

        def hook(count: float, block_size: float, total_size: float) -> None: ...

    with pbar:
        urlretrieve(url=url, filename=output_path, reporthook=hook)


def install(
    dest: Path | str = USER_DATA_MM_PATH,
    release: str = "latest-compatible",
    log_msg: _MsgLogger = _pretty_print,
    test_adapters: bool = False,
) -> None:
    """Install Micro-Manager to `dest`.

    Parameters
    ----------
    dest : Path | str, optional
        Where to install Micro-Manager, by default will install to a pymmcore-plus
        folder in the user's data directory: `appdirs.user_data_dir()`.
    release : str, optional
        Which release to install, by default "latest". Should be a date in the form
        YYYYMMDD, "latest" to install the latest nightly release, or "latest-compatible"
        to install the latest nightly release that is compatible with the
        device interface version of the current pymmcore version.
    log_msg : _MsgLogger, optional
        Callback to log messages, must have signature:
        `def logger(text: str, color: str = "", emoji: str = ""): ...`
        May ignore color and emoji.
    test_adapters : bool, optional
        Whether to install test adapters, by default False.
    """
    if test_adapters:
        _test_dev_install(dest=dest, release=release)
        return

    if PLATFORM not in ("Darwin", "Windows") or (
        PLATFORM == "Darwin" and MACH == "arm64"
    ):
        log_msg(
            f"Unsupported platform/architecture for nightly build: {PLATFORM}/{MACH}\n"
            "   (Downloading just test adapters) ...",
            "bold magenta",
            ":exclamation:",
        )
        _test_dev_install(dest=dest, release=release)
        return

    if release == "latest-compatible":
        # date when the device interface version FOLLOWING the version that this
        # pymmcore supports was released.
        next_div_date = INTERFACES.get(PYMMCORE_DIV + 1, None)

        # if div is equal to the greatest known interface version, use latest
        if PYMMCORE_DIV == max(INTERFACES.keys()) or next_div_date is None:
            release = "latest"
        else:  # pragma: no cover
            # otherwise, find the date of the release in available_versions() that
            # is less than the next_div date.
            available = available_versions()
            release = max(
                (date for date in available if date < next_div_date),
                default="unavailable",
            )
            if release == "unavailable":
                # fallback to latest if no compatible versions found
                raise ValueError(
                    "Unable to find a compatible release for device interface"
                    f"{PYMMCORE_DIV} at {DOWNLOADS_URL} "
                )

    if release == "latest":
        plat = {
            "Darwin": "macos/Micro-Manager-x86_64-latest.dmg",
            "Windows": "windows/MMSetup_x64_latest.exe",
        }[PLATFORM]
        url = f"{BASE_URL}/latest/{plat}"
    else:
        available = available_versions()
        if release not in available:
            n = 15
            avail = ", ".join(list(available)[:n]) + " ..."
            raise typer.BadParameter(
                f"Release {release!r} not found. Last {n} releases:\n{avail}"
            )
        url = available[release]

    with tempfile.TemporaryDirectory() as tmpdir:
        # download
        installer = Path(tmpdir) / url.split("/")[-1]
        log_msg(f"Downloading {url} ...", "bold blue")
        show_progress = log_msg is _pretty_print
        _download_url(url=url, output_path=installer, show_progress=show_progress)

        # install
        dest = Path(dest).expanduser().resolve()
        if PLATFORM == "Darwin":
            _mac_install(installer, dest, log_msg)
        elif PLATFORM == "Windows":
            # for windows, we need to know the latest version
            filename = _get_download_name(url)
            filename = filename.replace("MMSetup_64bit", "Micro-Manager")
            filename = filename.replace(".exe", "")
            _win_install(installer, dest / filename, log_msg)

    log_msg(f"Installed to {str(dest)!r}", "bold green", ":sparkles:")


if __name__ == "__main__":
    install()
