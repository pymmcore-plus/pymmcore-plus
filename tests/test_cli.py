from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from multiprocessing import Process, Queue
from time import sleep
from typing import Any, Callable, cast
from unittest.mock import Mock, patch

import pytest

try:
    from typer.testing import CliRunner

    from pymmcore_plus._cli import app
except ImportError:
    pytest.skip("cli extras not available", allow_module_level=True)

from pathlib import Path

from useq import MDASequence

from pymmcore_plus import CMMCorePlus, __version__, _cli, _logger, _util, install

runner = CliRunner()
subrun = subprocess.run

skipif_no_drivers_available = pytest.mark.skipif(
    platform.system() == "Linux"
    or (platform.system() == "Darwin" and platform.machine() == "arm64"),
    reason="Drivers not available on Linux or macOS ARM64",
)


def _mock_urlretrieve(url: str, filename: str, reporthook=None) -> None:
    """fake urlretrieve that writes a fake file."""
    with open(filename, "w") as f:
        f.write("test")
        reporthook(0, 0, 0)


def _mock_run(dest: Path) -> Callable:
    """fake subprocess that handles special cases to test `mmcore install`."""
    mnt = dest / "vol"
    mmdir = mnt / "Micro-Manager-2.0.0"

    def runner(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        if not args and args[0]:
            return subrun(*args, **kwargs)
        if args[0][0] == "hdiutil":
            if args[0][1] == "attach":
                mmdir.mkdir(parents=True)
                (mmdir / "ImageJ.app").touch()
                # the output of hdiutil attach is a list of lines
                # the last line is the name of the mount (which install uses)
                last_line = f"\t/dev/disk2s1\tApple_HFS\t{mnt}"
                return subprocess.CompletedProcess(args[0], 0, last_line.encode(), "")
            if args[0][1] == "detach":
                # hdiutil detach just cleans up the mount
                shutil.rmtree(mnt)
                return subprocess.CompletedProcess(args[0], 0, b"", "")
        if args[0][0] == "sudo":
            return subprocess.CompletedProcess(args[0], 0, b"", "")
        if args[0][0].endswith(".exe"):
            (dest / "Micro-Manager-2.0.0").mkdir(parents=True)
            (dest / "Micro-Manager-2.0.0" / "ImageJ.app").touch()
            return subprocess.CompletedProcess(args[0], 0, b"", "")
        return subrun(*args, **kwargs)

    return runner


@skipif_no_drivers_available
def test_install_app(tmp_path: Path) -> None:
    patch_download = patch.object(install, "urlretrieve", _mock_urlretrieve)
    patch_run = patch.object(subprocess, "run", _mock_run(tmp_path))

    with patch_download, patch_run:
        result = runner.invoke(app, ["install", "--dest", str(tmp_path)])
    assert (tmp_path / "Micro-Manager-2.0.0" / "ImageJ.app").exists()
    assert result.exit_code == 0


@skipif_no_drivers_available
def test_basic_install(tmp_path: Path) -> None:
    patch_download = patch.object(install, "urlretrieve", _mock_urlretrieve)
    patch_run = patch.object(subprocess, "run", _mock_run(tmp_path))
    # test calling install.install() with a simple message logger
    mock = Mock()
    with patch_download, patch_run:
        install.install(log_msg=mock)
    assert mock.call_args_list[0][0][0].startswith("Downloading")
    assert mock.call_args_list[-1][0][0].startswith("Installed")


@skipif_no_drivers_available
def test_available_versions() -> None:
    """installing with an erroneous version should fail and show available versions."""
    result = runner.invoke(app, ["install", "-r", "xxxx"])
    assert result.exit_code > 0
    msg = result.stdout or result.stderr
    assert "Release 'xxxx' not found" in msg
    assert "Last 15 releases:" in msg


def test_show_version() -> None:
    """show version should work."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "pymmcore-plus" in result.stdout
    assert __version__ in result.stdout
    assert "MMCore" in result.stdout


def test_clean(tmp_path: Path) -> None:
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


def test_list() -> None:
    """Just shows what's in the user data folder."""
    result = runner.invoke(app, ["list"])
    if result.exit_code != 0:
        raise AssertionError(
            "mmcore list failed... is Micro-Manager installed?  (run mmcore install)"
        )


def test_cli_use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mm = tmp_path / "mm"
    current = mm / ".current"
    monkeypatch.setattr(_util, "USER_DATA_MM_PATH", mm)
    monkeypatch.setattr(_util, "CURRENT_MM_PATH", current)

    # provide existing path
    fake = tmp_path / "fake-123456"
    fake.mkdir()
    runner.invoke(app, ["use", str(fake)])
    assert current.read_text() == str(fake)
    assert _util.find_micromanager() == str(fake)

    # match based on pattern
    runner.invoke(app, ["use", "1234"])
    assert current.read_text() == str(fake)

    # error if no match
    result = runner.invoke(app, ["use", "xyz"])
    assert result.exit_code > 0

    # error if not directory
    file = tmp_path / "file.txt"
    file.touch()
    result = runner.invoke(app, ["use", str(file)])
    assert result.exit_code > 0


ARGS: list[dict[str, dict | str]] = [
    {"z_plan": {"step": 0.24, "above": 1, "below": 2}},
    {"z_plan": {"step": 0.24, "range": 4}},
    {"z_plan": {"step": 0.24, "range": 4}, "time_plan": {"interval": 0.2, "loops": 20}},
    {"time_plan": {"interval": 0.2, "loops": 20}},
    {"axis_order": "TPCZ", "time_plan": {"interval": 0.2, "loops": 20}},
]


@pytest.mark.filterwarnings("ignore:.*got unknown keyword arguments:UserWarning")
@pytest.mark.parametrize("args", ARGS)
@pytest.mark.parametrize("with_file", (True, False))
def test_run_mda(tmp_path: Path, with_file: bool, args: dict[str, dict | str]) -> None:
    """Just runs a simple MDA."""

    cmd: list[str] = ["run"]
    for k, v in args.items():
        if isinstance(v, str):
            cmd.extend((f"--{k.replace('_', '-')}", str(v)))
        else:
            for kk, vv in v.items():
                cmd.extend((f"--{k[0]}-{kk.replace('_', '-')}", str(vv)))

    if with_file:
        seq = MDASequence(
            time_plan={"interval": 0.1, "loops": 10},
            channels=["DAPI", "FITC"],
            z_plan={"range": 6, "step": 1},
            axis_order="TPZC",
            metadata={"test": "test"},
        )
        useq_file = tmp_path / "test.json"
        useq_file.write_text(seq.model_dump_json())
        cmd.append(str(useq_file))

        for field_name, val in args.items():
            try:
                valid_field = getattr(MDASequence(**{field_name: val}), field_name)
            except TypeError:
                valid_field = None
            # when the args are a complete field on their own
            # it will replace the whole field
            if isinstance(val, str) or valid_field:
                seq = seq.replace(**{field_name: val})
            # otherwise it updates the existing
            else:
                _data = seq.model_dump() if hasattr(seq, "model_dump") else seq.dict()
                sub_field = cast("dict", _data[field_name])
                sub_field.update(**val)
                newval = getattr(MDASequence(**{field_name: sub_field}), field_name)
                seq = seq.replace(**{field_name: newval})
        expected = seq.model_copy() if hasattr(seq, "model_copy") else seq.copy()
    else:
        expected = MDASequence(**args)

    with patch("pymmcore_plus.core._mmcore_plus._instance") as mock:
        result = runner.invoke(app, cmd)

    assert result.exit_code == 0
    mock.run_mda.assert_called_with(expected)


def test_run_mda_dry() -> None:
    with patch("pymmcore_plus.core._mmcore_plus._instance") as mock:
        result = runner.invoke(app, ["run", "--dry-run"])

    assert result.exit_code == 0
    mock.run_mda.assert_not_called()


def test_run_mda_channels() -> None:
    FITC = {"config": "FITC", "exposure": 0.1, "do_stack": False, "group": "test"}
    cmd: list[str] = [
        "run",
        "--channel-group",
        "test",
        "--channel",
        "DAPI",
        "--channel",
        json.dumps(FITC),
        "--channel",
        "Other;70",
    ]
    with patch("pymmcore_plus.core._mmcore_plus._instance") as mock:
        result = runner.invoke(app, cmd)

    expected = MDASequence(
        channels=[
            {"group": "test", "config": "DAPI"},
            FITC,
            {"config": "Other", "exposure": 70, "group": "test"},
        ]
    )

    assert result.exit_code == 0
    mock.run_mda.assert_called_with(expected)

    # Running out app in SubProcess and after a while using signal sending
    # SIGINT, results passed back via channel/queue


# background process to test `logs --tail`
def _background_tail(q: Queue, runner: Any, logfile: Path) -> None:
    from os import getpid, kill
    from signal import SIGINT
    from threading import Timer

    from pymmcore_plus import _logger

    _logger.LOG_FILE = logfile

    Timer(0.2, lambda: kill(getpid(), SIGINT)).start()
    result = runner.invoke(app, ["logs", "--tail"], input="ctrl-c")
    q.put(result.output)


# make this test run last
# this test is a bit of a mess, but it's the best I can do for now
# the problem is that it leaves things in a state such that file descriptors are leaked
# by pretty much every test that creates a core after it.
@pytest.mark.skipif(bool(not os.getenv("CI")), reason="this is a crappy test")
@pytest.mark.run_last
@pytest.mark.filterwarnings("ignore:unclosed file:ResourceWarning")
def test_cli_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # create mock log file
    TEST_LOG = tmp_path / "test.log"
    monkeypatch.setattr(_logger, "LOG_FILE", TEST_LOG)
    _logger.configure_logging(file=TEST_LOG)
    assert _logger.current_logfile(_logger.logger) == TEST_LOG
    assert TEST_LOG.exists()

    # instantiate core
    core = CMMCorePlus()
    assert core.getPrimaryLogFile() == str(TEST_LOG)
    core.loadSystemConfiguration()
    # it may take a moment for the log file to be written
    time.sleep(0.2)
    # run mmcore logs
    result = runner.invoke(app, ["logs", "-n", "60"])
    assert result.exit_code == 0
    assert "IFO,Core" in result.output  # this will come from CMMCore

    # this one line depends critically on proper monkeypatching, and I can't get
    # the monkeypatch to work without causing lots of leaked file handle problems.
    # assert "Initialized" in result.output  # this will come from CMMCorePlus

    # run mmcore logs --tail
    # not sure how to kill the subprocess correctly on windows yet
    if os.name != "nt":
        q: Queue = Queue()
        p = Process(target=_background_tail, args=(q, runner, TEST_LOG))
        p.start()
        try:
            while p.is_alive():
                sleep(0.1)
            output = q.get()
            assert "IFO,Core" in output
        finally:
            p.terminate()
            p.join()  # Ensure the process is fully cleaned up

    runner.invoke(app, ["logs", "--clear"])
    if os.name != "nt":
        # this is also not clearing the file on windows... perhaps due to
        # in-use file?
        assert not TEST_LOG.exists()

    # cleanup all logging handlers
    _logger.configure_logging(file=None)
    for handler in _logger.logger.handlers:
        handler.close()
        _logger.logger.removeHandler(handler)


def test_cli_info() -> None:
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "pymmcore-plus" in result.stdout
    assert "python" in result.stdout
    assert "api-version-info" in result.stdout


def test_cli_bench() -> None:
    local = Path(__file__).parent / "local_config.cfg"
    result = runner.invoke(app, ["bench", "--config", str(local)])
    assert result.exit_code == 0
    assert "Loading config" in result.stdout
    assert "Core" in result.stdout
