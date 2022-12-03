import shutil
import subprocess
from pathlib import Path
from typing import Callable
from unittest.mock import patch

from pymmcore_plus import __version__, _cli
from pymmcore_plus._cli import app
from typer.testing import CliRunner

runner = CliRunner()
subrun = subprocess.run


def _mock_urlretrieve(url, filename, reporthook=None):
    """fake urlretrieve that writes a fake file."""
    with open(filename, "w") as f:
        f.write("test")
        reporthook(0, 0, 0)


def _mock_run(dest: Path) -> Callable:
    """fake subprocess that handles special cases to test `mmcore install`."""
    _tmp = dest / "vol" / "Micro-Manager-2.0.0"
    mmdir = dest / "Micro-Manager-2.0.0"

    def runner(*args, **kwargs) -> subprocess.CompletedProcess:
        if not args and args[0]:
            return subrun(*args, **kwargs)
        if args[0][0] == "hdiutil":
            if args[0][1] == "attach":
                _tmp.mkdir(parents=True)
                (_tmp / "ImageJ.app").touch()
                return subprocess.CompletedProcess(args[0], 0, str(dest).encode(), "")
            if args[0][1] == "detach":
                shutil.rmtree(_tmp)
                return subprocess.CompletedProcess(args[0], 0, b"", "")
        if args[0][0] == "sudo":
            return subprocess.CompletedProcess(args[0], 0, b"", "")
        if args[0][0].endswith(".exe"):
            # mock the windows install
            mmdir.mkdir(parents=True)
            (mmdir / "ImageJ.app").touch()
            return subprocess.CompletedProcess(args[0], 0, b"", "")
        return subrun(*args, **kwargs)

    return runner


def test_app(tmp_path: Path) -> None:
    patch_download = patch.object(_cli, "urlretrieve", _mock_urlretrieve)
    patch_run = patch.object(subprocess, "run", _mock_run(tmp_path))

    with patch_download as mock, patch_run as mock2:
        result = runner.invoke(app, ["install", "--dest", str(tmp_path)])
    assert (tmp_path / "Micro-Manager-2.0.0" / "ImageJ.app").exists()
    assert result.exit_code == 0


def test_available_versions(tmp_path: Path) -> None:
    """installing with an erroneous version should fail and show available versions."""
    result = runner.invoke(app, ["install", "-r", "xxxx"])
    assert result.exit_code > 0
    assert "Release 'xxxx' not found" in result.stdout
    assert "Last 15 releases:" in result.stdout


def test_show_version() -> None:
    """show version should work."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "pymmcore-plus" in result.stdout
    assert __version__ in result.stdout
    assert "MMCore" in result.stdout


def test_clean(tmp_path: Path):
    """Just cleans up the user data folder."""
    test_file = tmp_path / "test.txt"
    test_file.touch()
    _cli.USER_DATA_MM_PATH = tmp_path  # type: ignore
    assert test_file.exists()
    result = runner.invoke(app, ["clean"])
    assert result.exit_code == 0
    assert not test_file.exists()

    # this time nothing to clean
    result = runner.invoke(app, ["clean"])
    assert result.exit_code == 0


def test_list(tmp_path: Path):
    """Just shows what's in the user data folder."""
    empty_dir = tmp_path / "empty"
    _cli.USER_DATA_MM_PATH = empty_dir  # type: ignore
    result = runner.invoke(app, ["list"])
    assert "test.txt" not in result.stdout

    empty_dir.mkdir()
    test_file = empty_dir / "test.txt"
    test_file.touch()
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "test.txt" in result.stdout


def test_find(tmp_path: Path):
    # this should pass if any of the tests work :)
    # since we probably need to find mmore for anything to work!
    result = runner.invoke(app, ["find"])
    assert result.exit_code == 0
