import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager, suppress
from pathlib import Path
from platform import system
from typing import Dict, Iterator, Optional
from urllib.request import urlopen, urlretrieve

import pymmcore_plus
import typer
from pymmcore_plus._logger import set_log_level
from pymmcore_plus._util import USER_DATA_MM_PATH
from rich import print, progress


PLATFORM = system()
BASE_URL = "https://download.micro-manager.org"
_list = list

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _show_version_and_exit(value: bool) -> None:
    if value:
        import pymmcore

        typer.echo(f"pymmcore-plus v{pymmcore_plus.__version__}")
        typer.echo(f"pymmcore v{pymmcore.__version__}")  # type: ignore [attr-defined]
        typer.echo(f"MMCore v{pymmcore.CMMCore().getAPIVersionInfo()}")
        raise typer.Exit()


@app.callback()
def _main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=_show_version_and_exit,
        help="Show version and exit.",
        is_eager=True,
    ),
) -> None:
    """mmcore: pymmcore-plus command line (v{version}).

    For additional help on a specific command: type 'mmcore [command] --help'
    """


_main.__doc__ = typer.style(
    (_main.__doc__ or "").format(version=pymmcore_plus.__version__),
    fg=typer.colors.BRIGHT_YELLOW,
)


@app.command()
def clean() -> None:
    """Remove all Micro-Manager installs downloaded by pymmcore-plus."""
    if USER_DATA_MM_PATH.exists():
        for p in USER_DATA_MM_PATH.iterdir():
            shutil.rmtree(p, ignore_errors=True)
            print(f":wastebasket: [bold red] {p.name}")
        shutil.rmtree(USER_DATA_MM_PATH, ignore_errors=True)
    else:
        print(":sparkles: [bold green]No files to remove.")


@app.command()
def list() -> None:  # noqa: A001
    """Show all Micro-Manager installs downloaded by pymmcore-plus."""
    if USER_DATA_MM_PATH.exists():
        print(f":file_folder:[bold green] {USER_DATA_MM_PATH}")
        for path in USER_DATA_MM_PATH.iterdir():
            print(f"   • [cyan]{path.name}")
    else:
        print(":sparkles: [bold green]There are no pymmcore-plus Micro-Manager files.")


@app.command()
def find() -> None:
    """Show the location of Micro-Manager in use by pymmcore-plus."""
    set_log_level("CRITICAL")
    found = None
    with suppress(Exception):
        found = pymmcore_plus.find_micromanager(return_first=False)
    if found:
        first, *rest = found
        print(f":white_check_mark: [bold green]Using: {first}")
        if rest:
            print("\n[bold cyan](Also found):")
            for p in rest:
                print(f"   • [cyan]{p}")
        raise typer.Exit(0)
    print(":x: [bold red]No Micro-Manager installation found")
    print("[magenta]run `mmcore install` to install a version of Micro-Manager")
    raise typer.Exit(1)


@app.command()
def install(
    dest: Path = typer.Option(
        USER_DATA_MM_PATH,
        "-d",
        "--dest",
        file_okay=False,
        dir_okay=True,
        writable=True,
        resolve_path=True,
        help="Installation directory.",
    ),
    release: str = typer.Option(
        "latest", "-r", "--release", help="Release date. e.g. 20210201"
    ),
) -> None:
    """Install Micro-Manager Device adapters."""
    if PLATFORM not in ("Darwin", "Windows"):
        print(f":x: [bold red]Unsupported platform: {PLATFORM!r}")
        raise typer.Exit(1)

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
            avail = ", ".join(_list(available)[:n]) + " ..."
            raise typer.BadParameter(
                f"Release {release!r} not found. Last {n} releases:\n{avail}"
            )
        url = available[release]

    with tempfile.TemporaryDirectory() as tmpdir:
        _tmp_dest = Path(tmpdir) / "mm"
        _download_url(url=url, output_path=_tmp_dest)
        if PLATFORM == "Darwin":
            _mac_install(_tmp_dest, dest)
        elif PLATFORM == "Windows":
            _win_install(_tmp_dest, dest)

    print(f":sparkles: [bold green]Installed to {dest}![/bold green] :sparkles:")


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
    subprocess.run(
        [exe, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={dest}"],
        check=True,
    )


def _mac_install(dmg: Path, dest: Path) -> None:
    """Install Micro-Manager `dmg` to `dest`."""
    # with progress bar, mount dmg
    with _spinner("Mounting ..."):
        proc = subprocess.run(
            ["hdiutil", "attach", "-nobrowse", str(dmg)],
            capture_output=True,
        )
        if proc.returncode != 0:
            typer.secho(
                f"\nError mounting {dmg.name}:\n{proc.stderr.decode()}",
                fg="bright_red",
            )
            raise typer.Exit(code=proc.returncode)

    # with progress bar, mount dmg
    with _spinner(f"Installing to {dest} ..."):
        # get mount point
        mount = proc.stdout.splitlines()[-1].split()[-1].decode()
        try:
            try:
                src = next(Path(mount).glob("Micro-Manager*"))
            except StopIteration:
                typer.secho(
                    "\nError: Could not find Micro-Manager in dmg.\n"
                    "Please report this at https://github.com/pymmcore-plus/"
                    "pymmcore-plus/issues/new",
                    fg="bright_red",
                )
                raise typer.Exit(code=1) from None
            install_path = dest / src.name
            shutil.copytree(src, install_path, dirs_exist_ok=True)
        finally:
            subprocess.run(
                ["hdiutil", "detach", mount], check=True, capture_output=True
            )

    # fix gatekeeper ... requires password
    typer.secho(
        "(Your password may be required to install Micro-manager.)",
        fg=typer.colors.GREEN,
    )
    cmd = ["sudo", "xattr", "-r", "-d", "com.apple.quarantine", str(install_path)]
    subprocess.run(cmd, check=True)

    # # fix path randomization by temporarily copying elsewhere and back
    with tempfile.TemporaryDirectory() as tmpdir:
        _tmp = Path(tmpdir)
        os.rename(install_path / "ImageJ.app", _tmp / "ImageJ.app")
        os.rename(_tmp / "ImageJ.app", install_path / "ImageJ.app")


def _available_versions() -> Dict[str, str]:
    """Return a map of version -> url available for download."""
    plat = {"Darwin": "Mac", "Windows": "Windows"}[PLATFORM]
    with urlopen(f"{BASE_URL}/nightly/2.0/{plat}/") as resp:
        html = resp.read().decode("utf-8")

    return {
        ref.rsplit("-", 1)[-1].split(".")[0]: BASE_URL + ref
        for ref in re.findall(r"href=\"([^\"]+)\"", html)
        if ref != "/"
    }


def _download_url(url: str, output_path: Path = Path("thing")) -> None:
    """Download `url` to `output_path` with a nice progress bar."""
    import ssl

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


def main() -> None:
    app()
