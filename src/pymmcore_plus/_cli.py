import shutil
import sys
from contextlib import suppress
from pathlib import Path
from typing import Optional

import pymmcore_plus
import typer
from pymmcore_plus._logger import set_log_level
from pymmcore_plus._util import USER_DATA_MM_PATH
from pymmcore_plus.install import PLATFORM
from rich import print

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
    # fix for windows CI encoding and emoji printing
    if getattr(sys.stdout, "encoding", None) != "utf-8":
        with suppress(AttributeError):
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore [attr-defined]


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


@app.command(name="list")
def _list() -> None:
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
    else:  # pragma: no cover
        print(":x: [bold red]No Micro-Manager installation found")
        print("[magenta]run `mmcore install` to install a version of Micro-Manager")
        raise typer.Exit(1)


@app.command()
def mmgui() -> None:
    """Run the Java Micro-Manager GUI for the MM install returned by `mmcore find`."""
    import subprocess

    found = pymmcore_plus.find_micromanager()
    app = next(Path(found).glob("ImageJ*"), None) if found else None
    if not app:  # pragma: no cover
        print(":x: [bold red]No Micro-Manager installation found")
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
) -> None:
    """Install Micro-Manager Device adapters."""
    import pymmcore_plus.install

    pymmcore_plus.install._install(dest, release)


def main() -> None:
    app()
