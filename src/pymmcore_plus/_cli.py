# do NOT use __future__.annotations here. It breaks typer.
import os
import shutil
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import List, Optional, Union, cast

try:
    import typer
    from rich import print
except ImportError:  # pragma: no cover
    raise ImportError(
        'Please install with `pip install "pymmcore-plus[cli]"` to use the '
        "pymmcore-plus command line interface."
    ) from None

import pymmcore_plus
from pymmcore_plus._logger import configure_logging
from pymmcore_plus._util import USER_DATA_MM_PATH
from pymmcore_plus.install import PLATFORM

app = typer.Typer(no_args_is_help=True)


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
    # fix for windows CI encoding and emoji printing
    if getattr(sys.stdout, "encoding", None) != "utf-8":
        with suppress(AttributeError):
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore [attr-defined]


_main.__doc__ = typer.style(
    (_main.__doc__ or "").format(version=pymmcore_plus.__version__),
    fg=typer.colors.BRIGHT_YELLOW,
)


@app.command()
def clean(
    glob: str = typer.Argument(default="*", help="glob pattern to clean"),
) -> None:
    """Remove all Micro-Manager installs downloaded by pymmcore-plus."""
    if USER_DATA_MM_PATH.exists():
        for p in USER_DATA_MM_PATH.glob(glob):
            shutil.rmtree(p, ignore_errors=True)
            print(f":wastebasket: [bold red] {p.name}")
        shutil.rmtree(USER_DATA_MM_PATH, ignore_errors=True)
    else:
        print(":sparkles: [bold green]No files to remove.")


@app.command(name="list")
def _list() -> None:
    """Show all Micro-Manager installs downloaded by pymmcore-plus."""
    configure_logging(stderr_level="CRITICAL")
    found: dict[Path, list[str]] = {}
    with suppress(Exception):
        for p in pymmcore_plus.find_micromanager(return_first=False):
            pth = Path(p)
            found.setdefault(pth.parent, []).append(pth.name)

    if found:
        first = True
        for parent, items in found.items():
            print(f":file_folder:[bold green] {parent}")
            for item in items:
                bullet = "   [bold yellow]*" if first else "   •"
                print(f"{bullet} [cyan]{item}")
                first = False
    else:
        print(":x: [bold red]There are no pymmcore-plus Micro-Manager files.")
        print("[magenta]run `mmcore install` to install a version of Micro-Manager")


@app.command()
def mmstudio() -> None:  # pragma: no cover
    """Run the Java Micro-Manager GUI."""
    mm = pymmcore_plus.find_micromanager()
    app = (
        next((x for x in Path(mm).glob("ImageJ*") if not str(x).endswith("cfg")), None)
        if mm
        else None
    )
    if not app:  # pragma: no cover
        print(f":x: [bold red]No MMStudio application found in {mm!r}")
        print("[magenta]run `mmcore install` to install a version of Micro-Manager")
        raise typer.Exit(1)
    cmd = ["open", "-a", str(app)] if PLATFORM == "Darwin" else [str(app)]
    raise typer.Exit(subprocess.run(cmd).returncode)


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
    plain_output: bool = typer.Option(
        False,
        "--plain-output",
        help="Do not use rich output. Useful for scripting.",
        show_default=False,
    ),
) -> None:
    """Install Micro-Manager Device adapters."""
    import pymmcore_plus.install

    if plain_output:

        def _log_msg(text: str, color: str = "", emoji: str = "") -> None:
            print(text)

        pymmcore_plus.install.install(dest, release, log_msg=_log_msg)
    else:
        pymmcore_plus.install.install(dest, release)


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
    z_go_up: Optional[bool] = typer.Option(None, help="Acquire from bottom to top."),
    z_top: Optional[float] = typer.Option(None, help="Top of z-stack."),
    z_bottom: Optional[float] = typer.Option(None, help="Bottom of z-stack."),
    z_range: Optional[float] = typer.Option(
        None, help="Symmetric range of z-stack around position."
    ),
    z_above: Optional[float] = typer.Option(
        None, help="Asymmetric range of z-stack above position."
    ),
    z_below: Optional[float] = typer.Option(
        None, help="Asymmetric range of z-stack below position."
    ),
    z_step: Optional[float] = typer.Option(None, help="Step size of z-stack."),
    z_relative: Optional[List[float]] = typer.Option(
        None, "-zr", help="Relative z-positions to acquire (may use multiple times)."
    ),
    z_absolute: Optional[List[float]] = typer.Option(
        None, "-za", help="Absolute z-positions to acquire (may use multiple times)."
    ),
    t_interval: Optional[float] = typer.Option(
        None, help="Interval between timepoints."
    ),
    t_duration: Optional[float] = typer.Option(None, help="Duration of time lapse."),
    t_loops: Optional[float] = typer.Option(
        None, help="Number of time points to acquire."
    ),
    dry_run: bool = typer.Option(False, help="Do not run the acquisition."),
    axis_order: Optional[str] = typer.Option(
        None, help="Order of axes to acquire (e.g. 'TPCZ')."
    ),
    channel: Optional[List[str]] = typer.Option(
        None,
        help="\bChannel to acquire. Argument is a string of the following form:\n"
        '\b - name: "DAPI"\n'
        '\b - name;exposure: "DAPI;0.5"\n'
        '\b - useq-schema JSON: \'{"config": "DAPI", "exposure": 0.5, "z_offset": 0.5}\'',  # noqa: E501
    ),
    channel_group: str = typer.Option(
        "Channel", help="Name of Micro-Manager configuration group for channels."
    ),
) -> None:
    """Run a Micro-Manager acquisition from a useq-schema MDASequence file."""
    import json

    from useq import MDASequence

    # load from file if provided...
    if useq is None:
        mda = {}
    else:
        _mda = MDASequence.from_file(useq)
        mda = _mda.model_dump() if hasattr(_mda, "model_dump") else _mda.dict()

    # Any command line arguments take precedence over useq file
    # note that useq-schema itself will handle any conflicts between z plans
    # (the first correct Union of keyword arguments will win.)
    _zmap = (
        ("go_up", z_go_up),
        ("top", z_top),
        ("bottom", z_bottom),
        ("range", z_range),
        ("above", z_above),
        ("below", z_below),
        ("step", z_step),
        ("relative", z_relative),
        ("absolute", z_absolute),
    )
    if z_plan := {k: v for k, v in _zmap if v not in (None, [])}:
        try:
            # the field is valid on its own. overwrite:
            mda["z_plan"] = MDASequence(z_plan=z_plan).z_plan
        except Exception:
            # the field is not valid on its own. update existing:
            mda.setdefault("z_plan", {}).update(z_plan)

    _tmap = (("interval", t_interval), ("duration", t_duration), ("loops", t_loops))
    if time_plan := {k: v for k, v in _tmap if v is not None}:
        try:
            # the field is valid on its own. overwrite:
            mda["time_plan"] = MDASequence(time_plan=time_plan).time_plan
        except Exception:
            # the field is not valid on its own. update existing:
            mda.setdefault("time_plan", {}).update(time_plan)

    if axis_order is not None:
        mda["axis_order"] = axis_order

    for c in channel or []:
        try:
            # try to parse as JSON
            _c = json.loads(c)
        except json.JSONDecodeError:
            # try to parse as name;exposure
            name, *exposure = c.split(";")
            _c = {"config": name}
            if exposure:
                _c["exposure"] = float(exposure[0])
        mda.setdefault("channels", []).append(_c)
    if channel_group is not None:
        for c in mda.get("channels", []):
            cast(dict, c)["group"] = channel_group

    # this will raise if anything has gone wrong.
    _mda = MDASequence(**mda)

    if dry_run:
        print(":eyes: [bold green]Would run\n")
        print(_mda.model_dump() if hasattr(_mda, "model_dump") else _mda.dict())
        raise typer.Exit(0)

    core = pymmcore_plus.CMMCorePlus.instance()
    core.loadSystemConfiguration(config or "MMConfig_demo.cfg")
    core.run_mda(_mda)


@app.command()
def build_dev(
    devices: Optional[List[str]] = typer.Argument(
        None, help="Device adapters to build. Defaults to DemoCamera and Utilities."
    ),
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
    overwrite: Optional[bool] = typer.Option(
        None,
        "-y",
        help="Overwrite existing if git sha is already built. "
        "If not specified, will prompt.",
    ),
) -> None:  # pragma: no cover
    """Build DemoCamera and Utility adapters from source for apple silicon."""
    from pymmcore_plus._build import DEFAULT_PACKAGES, build

    devices = DEFAULT_PACKAGES if not devices else devices
    print(f"Building {devices}\ninto {str(dest)!r}")
    try:
        build(dest, overwrite=overwrite, devices=devices)
    except Exception as e:
        print(f":x: [bold red]{e}")
        raise typer.Exit(1) from e


@app.command()
def logs(
    num: Optional[int] = typer.Option(
        None, "-n", "--num", help="Number of lines to display."
    ),
    tail: bool = typer.Option(False, "-t", "--tail", help="Continually stream logs."),
    clear: bool = typer.Option(False, "-c", "--clear", help="Delete all log files."),
    reveal: bool = typer.Option(
        False, "--reveal", help="Reveal log file in Explorer/Finder."
    ),
) -> None:
    """Display recent output from pymmcore-plus log."""
    # NOTE: technically LOG_FILE may not be the active log if the user configured
    # logging manually. But this is a reasonable default.  To really know this, in
    # a cross-process safe way, we would need to write the path to the active log file
    # in a file in the user data directory.
    from ._logger import LOG_FILE

    if not LOG_FILE or not LOG_FILE.exists():
        print(":sparkles: [bold green]No log file.")
        raise typer.Exit(0)

    if reveal:  # pragma: no cover
        if os.name == "nt":  # Windows
            subprocess.run(["explorer", "/select,", str(LOG_FILE)])
        elif os.name == "posix":  # macOS or Linux
            subprocess.run(["open", "-R", str(LOG_FILE)])

        raise typer.Exit(0)

    if clear:
        for f in LOG_FILE.parent.glob("*.log"):
            f.unlink()
            print(f":wastebasket: [bold red] Cleared log file {f}")
        raise typer.Exit(0)

    if tail:
        _tail_file(LOG_FILE)
    else:
        with open(LOG_FILE) as fh:
            lines = fh.readlines()
        if num:
            lines = lines[-num:]
        for line in lines:
            print(line.strip())


@app.command()
def info() -> None:
    """Display information about the Micro-Manager and pymmcore install."""
    from pymmcore_plus._util import system_info

    info = system_info()
    length = max(len(k) for k in info) + 1
    for key, value in info.items():
        typer.secho(f"{key:{length}}: {value}")


def _tail_file(file_path: Union[str, Path], interval: float = 0.1) -> None:
    with open(file_path) as file:
        # Move the file pointer to the end
        while True:
            # Read new lines
            new_lines = file.readlines()
            if new_lines:
                # Display the last 'num_lines' lines
                print("".join(new_lines), end="")

            # Sleep for a short interval before checking again
            time.sleep(1)


def main() -> None:  # pragma: no cover
    app()
