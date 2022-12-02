import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager, suppress
from pathlib import Path
from platform import system
from typing import Dict, Iterator, List, Optional, cast
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
        _mac_install(_tmp_dest, dest)

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
    subprocess.run(
        ["sudo", "xattr", "-r", "-d", "com.apple.quarantine", str(install_path)],
        check=True,
    )

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


@app.command()
def run(
    useq: Optional[Path] = typer.Argument(
        None,
        dir_okay=False,
        exists=True,
        resolve_path=True,
        help="Path to useq-schema file.",
    ),
    config: Optional[Path] = typer.Option(
        None,
        "-c",
        "--config",
        dir_okay=False,
        exists=True,
        resolve_path=True,
        help="Path to Micro-Manager system configuration file.",
    ),
    z_go_up: Optional[bool] = typer.Option(
        None,
        help="Acquire from bottom to top.",
    ),
    z_top: Optional[float] = typer.Option(
        None,
        help="Top of z-stack.",
    ),
    z_bottom: Optional[float] = typer.Option(
        None,
        help="Bottom of z-stack.",
    ),
    z_range: Optional[float] = typer.Option(
        None,
        help="Symmetric range of z-stack around position.",
    ),
    z_above: Optional[float] = typer.Option(
        None,
        help="Asymmetric range of z-stack above position.",
    ),
    z_below: Optional[float] = typer.Option(
        None,
        help="Asymmetric range of z-stack below position.",
    ),
    z_step: Optional[float] = typer.Option(
        None,
        help="Step size of z-stack.",
    ),
    z_relative: Optional[List[float]] = typer.Option(
        None,
        "-zr",
        help="Relative z-positions to acquire (may use multiple times).",
    ),
    z_absolute: Optional[List[float]] = typer.Option(
        None,
        "-za",
        help="Absolute z-positions to acquire (may use multiple times).",
    ),
    t_interval: Optional[float] = typer.Option(
        None,
        help="Interval between timepoints.",
    ),
    t_duration: Optional[float] = typer.Option(
        None,
        help="Duration of time lapse.",
    ),
    t_loops: Optional[float] = typer.Option(
        None,
        help="Number of time points to acquire.",
    ),
    dry_run: bool = typer.Option(
        False,
        help="Do not run the acquisition.",
    ),
    axis_order: Optional[str] = typer.Option(
        None,
        help="Order of axes to acquire (e.g. 'TPCZ').",
    ),
    channel: Optional[List[str]] = typer.Option(
        None,
        help="\bChannel to acquire. Argument is a string of the following form:\n"
        '\b - name: "DAPI"\n'
        '\b - name;exposure: "DAPI;0.5"\n'
        '\b - useq-schema JSON: \'{"config": "DAPI", "exposure": 0.5, "z_offset": 0.5}\'',  # noqa: E501
    ),
    channel_group: str = typer.Option(
        "Channel",
        help="Name of Micro-Manager configuration group for channels.",
    ),
) -> None:
    import json

    from useq import MDASequence

    # load from file if provided...
    mda = {} if useq is None else MDASequence.parse_file(useq).dict()

    # Any command line arguments take precedence over useq file
    # note that useq-schema itself will handle any conflicts between z plans
    # (the first correct Union of keyword arguments will win.)
    if z_go_up is not None:
        mda.setdefault("z_plan", {})["go_up"] = z_go_up
    if z_top is not None:
        mda.setdefault("z_plan", {})["top"] = z_top
    if z_bottom is not None:
        mda.setdefault("z_plan", {})["bottom"] = z_bottom
    if z_range is not None:
        mda.setdefault("z_plan", {})["range"] = z_range
    if z_above is not None:
        mda.setdefault("z_plan", {})["above"] = z_above
    if z_below is not None:
        mda.setdefault("z_plan", {})["below"] = z_below
    if z_step is not None:
        mda.setdefault("z_plan", {})["step"] = z_step
    if z_relative is not None:
        mda.setdefault("z_plan", {})["relative"] = z_relative
    if z_absolute is not None:
        mda.setdefault("z_plan", {})["absolute"] = z_absolute

    if t_interval is not None:
        mda.setdefault("time_plan", {})["interval"] = t_interval
    if t_duration is not None:
        mda.setdefault("time_plan", {})["duration"] = t_duration
    if t_loops is not None:
        mda.setdefault("time_plan", {})["loops"] = t_loops

    if axis_order is not None:
        mda["axis_order"] = axis_order

    if channel is not None:
        for c in channel:
            try:
                _c = json.loads(c)
            except json.JSONDecodeError:
                name, *exposure = c.split(";")
                _c = {"config": name}
                if exposure:
                    _c["exposure"] = float(exposure[0])
            mda.setdefault("channels", []).append(_c)
    if channel_group is not None:
        for c in mda.get("channels", []):
            cast(dict, c)["group"] = channel_group

    _mda = MDASequence(**mda)

    if dry_run:
        print(":eyes: [bold green]Would run\n")
        print(_mda.dict())
        raise typer.Exit(0)

    core = pymmcore_plus.CMMCorePlus.instance()
    core.loadSystemConfiguration(config or "MMConfig_demo.cfg")
    core.run_mda(_mda)


def main() -> None:
    app()
