"""Clone the micro-manager source code from GitHub and build dev devices."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.request import Request, urlopen

from rich import print
from rich.prompt import Prompt

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

MM_REPO = "micro-manager/micro-manager"
MMCORE_AND_DEV = "micro-manager/mmCoreAndDevices"
MM_REPO_URL = f"https://github.com/{MM_REPO}.git"
SYSTEM = platform.system()
MACHINE = platform.machine()
DEFAULT_PACKAGES = ["DemoCamera", "Utilities", "SequenceTester"]
M4_DEV_PATTERN = re.compile(
    r"m4_define\(\[device_adapter_dirs\],\s?\[m4_strip\(\[(.*)\]\)\]\)", re.DOTALL
)


def build(
    dest: Path,
    overwrite: bool | None = None,
    devices: Sequence[str] = DEFAULT_PACKAGES,
) -> None:
    """Build Micro-Manager device adapters from the git repo.

    Currently only supports macos and linux.
    Run on command line with `mmcore build-dev`

    Parameters
    ----------
    dest : Path
        Destination directory for the built adapters.
    overwrite : bool | None
        Whether to overwrite an existing installation. If `None`, will prompt.
    devices : Sequence[str]
        List of device adapters to build. Defaults to `["DemoCamera", "Utilities"]`.
        NOTE: not all device adapters will build successfully currently.
    """
    if SYSTEM == "Darwin":
        return _build_macos(dest, overwrite, devices)
    if SYSTEM == "Linux":
        return _build_linux(dest, overwrite, devices)
    raise NotImplementedError(
        f"Building on {SYSTEM} {MACHINE} is not currently supported."
    )


def _require(command: str, link: str = "") -> None:
    if not shutil.which(command):
        print(f"{command!r} is required but not found. Please install it first. {link}")
        return


def _build_macos(dest: Path, overwrite: bool | None, devices: Sequence[str]) -> None:
    _validate_device_list(devices)
    _require("brew", "https://brew.sh")
    _require("git")

    deps = [
        "autoconf",
        "automake",
        "libtool",
        "boost",
        "pkg-config",
        "autoconf-archive",
    ]
    if "SequenceTester" in devices:
        deps.append("msgpack-cxx")

    for dep in deps:
        output = subprocess.run(["brew", "ls", "--versions", dep], capture_output=True)
        if not output.stdout:
            ok = input(f"Dependency {dep!r} is not installed. Install? [y/N] ")
            if ok.lower() in ("y", "yes"):
                subprocess.run(["brew", "install", dep], check=True)
            else:
                print("Aborting.")
                return

    HOMEBREW_PREFIX = os.getenv("HOMEBREW_PREFIX", "/opt/homebrew")
    os.environ["LDFLAGS"] = f"-L{HOMEBREW_PREFIX}/lib/ -Wl,-rpath,'$ORIGIN'"
    os.environ["CPPFLAGS"] = f"-I{HOMEBREW_PREFIX}/include/"
    _make_install(
        dest,
        overwrite,
        devices,
        config_flags=[
            f"--with-boost={HOMEBREW_PREFIX}/include",
            f"--with-boost-libdir={HOMEBREW_PREFIX}/lib",
        ],
    )


def _build_linux(dest: Path, overwrite: bool | None, devices: Sequence[str]) -> None:
    _validate_device_list(devices)

    _require("git")

    need = [
        "build-essential",
        "autoconf",
        "autoconf-archive",
        "automake",
        "libtool",
        "pkg-config",
        "libboost-all-dev",
        # "swig3.0",
    ]
    if "SequenceTester" in devices:
        need.append("libmsgpack-dev")

    print("sudo will required to install the following packages:\n\t")
    print(", ".join(need))

    subprocess.run(["sudo", "apt-get", "update"], check=True)
    subprocess.run(["sudo", "apt-get", "-y", "install", *need], check=True)

    _make_install(dest, overwrite, devices)


def _make_install(
    dest: Path,
    overwrite: bool | None,
    devices: Sequence[str],
    config_flags: Sequence[str] | None = None,
) -> None:
    """Run the make and make install steps for building the devices.

    Works for both macos and linux.

    Parameters
    ----------
    dest : Path
        Destination directory for the built adapters. Adapters are built in a
        subdirectory named Micro-Manager-<sha> (where <sha> is the current commit hash
        of the repo).
    overwrite : bool | None
        If False, will not overwrite an existing installation.
        If True, will delete the existing installation.
        If None, will prompt the user.
    devices : Sequence[str]
        A list of device adapters to build. If a device is not recognized as a valid
        device adapter, a ValueError will be raised.
    config_flags : Sequence[str] | None
        Additional flags to pass to the `configure` command.
    """
    if not (sub_dest := _ensure_subdir(dest, overwrite)):
        return

    print(f"Building devices: {', '.join(devices)}\nInto {str(sub_dest)!r}\n")

    with _mm_repo_tmp_path() as repo_path:
        # update the configure.ac and Makefile.am files
        # to include only the devices requested
        devAdapters = repo_path / "mmCoreAndDevices" / "DeviceAdapters"
        (devAdapters / "Makefile.am").write_text(_build_makefile_am(devices))
        configure_ac = devAdapters / "configure.ac"
        configure_ac.write_text(_build_configure_ac(devices, configure_ac))

        # run make and make install
        subprocess.run(["./autogen.sh"], check=True)
        config_cmd = ["./configure", f"--prefix={repo_path.parent}", "--without-java"]
        config_cmd.extend(config_flags or [])
        subprocess.run(config_cmd, check=True)

        subprocess.run(["make"], check=True)
        subprocess.run(["make", "install"], check=True)

        # copy the built adapters to the destination
        built_libs = repo_path.parent / "lib" / "micro-manager"
        shutil.copytree(built_libs, sub_dest)

        # grab the demo config file to sub_dest
        demo_cfg = repo_path / "bindist" / "any-platform" / "MMConfig_demo.cfg"
        shutil.copy(demo_cfg, sub_dest)

    print(f":sparkles: [bold green]Installed to {dest}[/bold green] :sparkles:")


@contextmanager
def _mm_repo_tmp_path(git_repo_url: str = MM_REPO_URL) -> Iterator[Path]:
    """Context manager to clone the micro-manager repo and yield the path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        cmd = ["git", "clone", "--recurse-submodules", git_repo_url]
        subprocess.run(cmd, cwd=tmpdir, check=True)

        repo_path = tmp_path / "micro-manager"
        os.chdir(repo_path)
        yield repo_path


def _ensure_subdir(dest: Path, overwrite: bool | None = None) -> Path | None:
    """Pick destination subdir (with git sha) and check if it exists.

    If overwrite is False, return None.
    If overwrite is True, delete the existing directory.
    If overwrite is None, prompt the user.
    """
    subdest = dest / f"Micro-Manager-{_fetch_current_sha()}"

    # check if dest exists and maybe overwrite
    if subdest.exists():
        if overwrite is False:
            print(
                f"Destination '{subdest}' already exists and overwrite is False. "
                "Aborting."
            )
            return None
        elif overwrite:
            shutil.rmtree(subdest)
        else:
            delete = Prompt.ask(
                f"[yellow]Destination '{subdest}' already exists. Delete?",
                choices=["y", "n"],
                default="n",
            )
            if delete.lower() in ("y", "yes"):
                shutil.rmtree(subdest)
            else:
                print("[red]Aborting.")
                return None
    return subdest


# https://github.com/micro-manager/mmCoreAndDevices/blob/main/DeviceAdapters/Makefile.am
def _build_makefile_am(devices: Sequence[str]) -> str:
    """Create a new Makefile.am file with the device list inserted."""
    make_text = "AUTOMAKE_OPTIONS = foreign\nACLOCAL_AMFLAGS = -I ../m4\nSUBDIRS = "
    make_text += " ".join(devices)
    return make_text


# https://github.com/micro-manager/mmCoreAndDevices/blob/main/DeviceAdapters/configure.ac
def _build_configure_ac(devices: Sequence[str], template: str | Path) -> str:
    """Create a new configure.ac file with the device list inserted."""
    if isinstance(template, Path):
        template = template.read_text()

    # find the string m4_define([device_adapter_dirs], [m4_strip([...])])
    # and insert the device list

    devlist = " ".join(devices)
    insert = f"m4_define([device_adapter_dirs], [m4_strip([{devlist}])])"
    if not M4_DEV_PATTERN.search(template):
        raise ValueError(
            "Could not find the 'device_adapter_dirs' definition in the configure.ac "
            "file. This is unexpected and should be reported as a bug."
        )
    return M4_DEV_PATTERN.sub(insert, template)


def _validate_device_list(
    devices: Sequence[str], known_devices: Path | set[str] | None = None
) -> None:
    """Validate the list of device adapters against folders in DeviceAdapters."""
    if known_devices is None:
        # get the list of known devices from the GitHub repo
        known_devices = _fetch_available_device_list()
    elif isinstance(known_devices, Path):
        known_devices = {
            d.name
            for d in known_devices.iterdir()
            if d.is_dir() and (d / "Makefile.am").exists()
        }

    if unknown := set(devices) - set(known_devices):
        raise ValueError(
            f"The following devices names are not recognized: {sorted(unknown)}.\n\n"
            f"Valid device names are: {', '.join(sorted(known_devices))}.\n"
        )


def _gh_api_request(url: str) -> Request:
    """Create a request object with the appropriate headers for the GitHub API.

    Will look for a GH_API_TOKEN or GITHUB_TOKEN environment variable and add it to the
    request headers if found.
    """
    req = Request(url)
    if token := (os.getenv("GH_API_TOKEN") or os.getenv("GITHUB_TOKEN")):
        req.add_header("Authorization", f"token {token}")
    return req


def _fetch_available_device_list() -> set[str]:
    """Fetch the list of device adapters from the GitHub repo.

    Note that this doesn't restrict the set to only those with Makefile.am files.s
    """
    req = _gh_api_request(
        f"https://api.github.com/repos/{MMCORE_AND_DEV}/contents/DeviceAdapters"
    )
    with urlopen(req) as response:
        data = json.load(response)
    return {d["name"] for d in data if d["type"] == "dir"}


def _fetch_current_sha(short: bool = True) -> str:
    """Fetch sha of last commit to main on MM github repo."""
    req = _gh_api_request(f"https://api.github.com/repos/{MM_REPO}/commits/main")
    with urlopen(req) as response:
        data = json.load(response)

    sha = data["sha"]
    return sha[:7] if short else sha  # type: ignore
