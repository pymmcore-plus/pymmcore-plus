from __future__ import annotations

import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
from contextlib import contextmanager, nullcontext
from pathlib import Path
from platform import system
from typing import TYPE_CHECKING, Callable, ContextManager, Iterator, Protocol
from urllib.request import urlopen, urlretrieve

import typer

from pymmcore_plus._util import USER_DATA_MM_PATH

if TYPE_CHECKING:

    class _MsgLogger(Protocol):
        def __call__(self, text: str, color: str = "", emoji: str = "") -> None:
            ...


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
    def _spinner(
        text: str = "", color: str = "bold blue"
    ) -> Iterator[progress.Progress]:
        with progress.Progress(
            progress.SpinnerColumn(), progress.TextColumn(f"[{color}]{text}")
        ) as pbar:
            pbar.add_task(description=text, total=None)
            yield pbar

except ImportError:  # pragma: no cover
    progress = None

    def _pretty_print(text: str, color: str = "", emoji: str = "") -> None:
        print(text)

    @contextmanager
    def _spinner(text: str = "", color: str = "") -> Iterator[None]:
        print(text)
        yield


PLATFORM = system()
BASE_URL = "https://download.micro-manager.org"
_version_regex = re.compile(r"(\d+\.){2}\d+")


def _get_download_name(url: str) -> str:
    """Return the name of the file to be downloaded from `url`."""
    with urlopen(url) as tmp:
        content: str = tmp.headers.get("Content-Disposition")
        for part in content.split(";"):
            if "filename=" in part:
                return part.split("=")[1].strip('"')
    return ""


def _get_spinner(log_msg: _MsgLogger) -> Callable[[str], ContextManager[None]]:
    if log_msg is _pretty_print:
        spinner = _spinner
    else:

        @contextmanager
        def spinner(msg: str) -> Iterator[None]:
            log_msg(msg)
            yield

    return spinner


def _win_install(exe: Path, dest: Path, log_msg: _MsgLogger) -> None:
    spinner = _get_spinner(log_msg)
    cmd = [str(exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={dest}"]
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


def available_versions() -> dict[str, str]:
    """Return a map of version -> url available for download."""
    plat = {"Darwin": "Mac", "Windows": "Windows"}[PLATFORM]
    with urlopen(f"{BASE_URL}/nightly/2.0/{plat}/") as resp:
        html = resp.read().decode("utf-8")

    return {
        ref.rsplit("-", 1)[-1].split(".")[0]: BASE_URL + ref
        for ref in re.findall(r"href=\"([^\"]+)\"", html)
        if ref != "/"
    }


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
        pbar = nullcontext()

        def hook(count: float, block_size: float, total_size: float) -> None:
            ...

    with pbar:
        urlretrieve(url=url, filename=output_path, reporthook=hook)


def install(
    dest: Path | str = USER_DATA_MM_PATH,
    release: str = "latest",
    log_msg: _MsgLogger = _pretty_print,
) -> None:
    """Install Micro-Manager to `dest`.

    Parameters
    ----------
    dest : Path | str, optional
        Where to install Micro-Manager, by default will install to a pymmcore-plus
        folder in the user's data directory: `appdirs.user_data_dir()`.
    release : str, optional
        Which release to install, by default "latest". Should be a date in the form
        YYYYMMDD, or "latest" to install the latest nightly release.
    log_msg : _MsgLogger, optional
        Callback to log messages, must have signature:
        `def logger(text: str, color: str = "", emoji: str = ""): ...`
        May ignore color and emoji.
    """
    if PLATFORM not in ("Darwin", "Windows"):  # pragma: no cover
        log_msg(f"Unsupported platform: {PLATFORM!r}", "bold red", ":x:")
        raise sys.exit(1)

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
