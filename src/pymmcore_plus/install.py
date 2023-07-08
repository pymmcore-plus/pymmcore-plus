from __future__ import annotations

import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from platform import system
from typing import Iterator
from urllib.request import urlopen, urlretrieve

import typer
from rich import print, progress

from pymmcore_plus._util import USER_DATA_MM_PATH

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


@contextmanager
def _spinner(
    text: str = "Processing...", color: str = "bold blue"
) -> Iterator[progress.Progress]:
    with progress.Progress(
        progress.SpinnerColumn(),
        progress.TextColumn(f"[{color}]{text}"),
        transient=True,
    ) as pbar:
        pbar.add_task(description=text, total=None)
        yield pbar


def _win_install(exe: Path, dest: Path) -> None:
    cmd = [str(exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={dest}"]
    with _spinner("Installing ..."):
        subprocess.run(cmd, check=True)


def _mac_install(dmg: Path, dest: Path) -> None:
    """Install Micro-Manager `dmg` to `dest`."""
    # with progress bar, mount dmg
    with _spinner(f"Mounting {dmg.name} ..."):
        proc = subprocess.run(
            ["hdiutil", "attach", "-nobrowse", str(dmg)],
            capture_output=True,
        )
        if proc.returncode != 0:  # pragma: no cover
            print(f"\n[bold red]Error mounting {dmg.name}:\n{proc.stderr.decode()}")
            sys.exit(1)

    # with progress bar, mount dmg
    with _spinner(f"Installing to {dest} ..."):
        # get mount point
        mount = proc.stdout.splitlines()[-1].split()[-1].decode()
        try:
            try:
                src = next(Path(mount).glob("Micro-Manager*"))
            except StopIteration:  # pragma: no cover
                print(
                    "[bold red]\nError: Could not find Micro-Manager in dmg.\n"
                    "Please report this at https://github.com/pymmcore-plus/"
                    "pymmcore-plus/issues/new",
                )
                sys.exit(1)
            install_path = dest / src.name
            shutil.copytree(src, install_path, dirs_exist_ok=True)
        finally:
            subprocess.run(
                ["hdiutil", "detach", mount], check=True, capture_output=True
            )

    # fix gatekeeper ... requires password
    print("[green](Your password may be required to install Micro-manager.)")
    cmd = ["sudo", "xattr", "-r", "-d", "com.apple.quarantine", str(install_path)]
    subprocess.run(cmd, check=True)

    # # fix path randomization by temporarily copying elsewhere and back
    with tempfile.TemporaryDirectory() as tmpdir:
        _tmp = Path(tmpdir)
        os.rename(install_path / "ImageJ.app", _tmp / "ImageJ.app")
        os.rename(_tmp / "ImageJ.app", install_path / "ImageJ.app")


def _available_versions() -> dict[str, str]:
    """Return a map of version -> url available for download."""
    plat = {"Darwin": "Mac", "Windows": "Windows"}[PLATFORM]
    with urlopen(f"{BASE_URL}/nightly/2.0/{plat}/") as resp:
        html = resp.read().decode("utf-8")

    return {
        ref.rsplit("-", 1)[-1].split(".")[0]: BASE_URL + ref
        for ref in re.findall(r"href=\"([^\"]+)\"", html)
        if ref != "/"
    }


def _download_url(url: str, output_path: Path) -> None:
    """Download `url` to `output_path` with a nice progress bar."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

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

    print(f"[bold blue]Downloading {url} ...")
    with pbar:
        urlretrieve(url=url, filename=output_path, reporthook=hook)


def _install(dest: Path, release: str) -> None:
    if PLATFORM not in ("Darwin", "Windows"):  # pragma: no cover
        print(f":x: [bold red]Unsupported platform: {PLATFORM!r}")
        raise sys.exit(1)

    if release == "latest":
        plat = {
            "Darwin": "macos/Micro-Manager-x86_64-latest.dmg",
            "Windows": "windows/MMSetup_x64_latest.exe",
        }[PLATFORM]
        url = f"{BASE_URL}/latest/{plat}"
    else:
        available = _available_versions()
        if release not in available:
            n = 15
            avail = ", ".join(list(available)[:n]) + " ..."
            raise typer.BadParameter(
                f"Release {release!r} not found. Last {n} releases:\n{avail}"
            )
        url = available[release]

    with tempfile.TemporaryDirectory() as tmpdir:
        installer = Path(tmpdir) / url.split("/")[-1]
        _download_url(url=url, output_path=installer)
        if PLATFORM == "Darwin":
            _mac_install(installer, dest)
        elif PLATFORM == "Windows":
            # for windows, we need to know the latest version
            filename = _get_download_name(url)
            filename = filename.replace("MMSetup_64bit", "Micro-Manager")
            filename = filename.replace(".exe", "")
            _win_install(installer, dest / filename)

    print(f":sparkles: [bold green]Installed to {dest}![/bold green] :sparkles:")


def _existing_dir(string: str) -> Path:
    path = Path(string)
    if not path.is_dir():
        raise NotADirectoryError(string)
    return path


def _version(value: str) -> str:
    if not _version_regex.match(value):
        raise ValueError(
            f"Invalid version: {value}. Must be of form x.y.z with x y and z in 0-9"
        )
    return value


def _release(value: str) -> str:
    if value.lower() == "latest":
        return "latest"
    if len(value) != 8:
        raise ValueError(f"Invalid date: {value}. Must be eight digits.")
    return str(value)


def main() -> None:  # pragma: no cover
    """Main entry point for the console_scripts."""
    import argparse

    from rich.panel import Panel

    print(
        Panel(
            ':exclamation: [bold red]"python -m pymmcore_plus.install" is deprecated. '
            'Use "mmcore install" instead :eyes:',
            border_style="red",
        )
    )

    parser = argparse.ArgumentParser(description="MM Device adapter installer.")
    parser.add_argument(
        "-d",
        "--dest",
        default=USER_DATA_MM_PATH,
        type=_existing_dir,
        help=f"Directory in which to install (default: {USER_DATA_MM_PATH})",
    )

    parser.add_argument(  # unused
        "-v",
        "--version",
        metavar="VERSION",
        type=_version,
        default="2.0.1",
        help="Version number. e.g. 2.0.1 - ignored if release=latest (default: 2.0.1)",
    )
    parser.add_argument(
        "-r",
        "--release",
        metavar="DATE",
        type=_release,
        default="latest",
        help='8 digit date (YYYYMMDD) of MM nightly build to fetch, or "latest" '
        "(default: latest)",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=False,
        help="Say yes to all prompts. (no input mode).",
    )

    args = parser.parse_args()
    _install(Path(args.dest), args.release)


if __name__ == "__main__":
    main()
