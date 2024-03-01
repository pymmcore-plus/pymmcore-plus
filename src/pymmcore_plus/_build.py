"""Clone the micro-manager source code from GitHub and build dev devices."""

import os
import platform
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from rich import print
from rich.prompt import Prompt

MM_REPO = "https://github.com/micro-manager/micro-manager.git"
SYSTEM = platform.system()
MACHINE = platform.machine()

# DemoCamera and Utilities are currently hard coded in here, but could
# be made configurable in the future.

# https://github.com/micro-manager/mmCoreAndDevices/blob/main/DeviceAdapters/Makefile.am
_MINIMAL_MAKE = r"""
AUTOMAKE_OPTIONS = foreign
ACLOCAL_AMFLAGS = -I ../m4
SUBDIRS = DemoCamera Utilities
"""

# https://github.com/micro-manager/mmCoreAndDevices/blob/main/DeviceAdapters/configure.ac
_MINIMAL_CONFIG = r"""
AC_PREREQ([2.69])
AC_INIT([Micro-Manager], [2])
AC_CONFIG_MACRO_DIR([../m4])
AC_CONFIG_SRCDIR([DemoCamera/DemoCamera.cpp])
AC_CANONICAL_HOST
AM_INIT_AUTOMAKE([foreign 1.11])
LT_PREREQ([2.2.6])
LT_INIT([disable-static])
AC_PROG_CC([cc gcc clang])
AC_PROG_CXX([c++ g++ clang++])
AX_CXX_COMPILE_STDCXX([14], [noext])

# Find Micro-Manager headers
micromanager_cpp_path=${ac_pwd}/..
micromanager_path=${micromanager_cpp_path}/..
MMDEVAPI_CXXFLAGS="-I${micromanager_cpp_path}/MMDevice ${BOOST_CPPFLAGS}"
AC_SUBST(MMDEVAPI_CXXFLAGS)

# Find Micro-Mana:ger static device library
MMDEVAPI_LIBADD="${micromanager_cpp_path}/MMDevice/libMMDevice.la"
AC_SUBST(MMDEVAPI_LIBADD)

# Apply appropriate libtool options for the Micro-Manager device API
MMDEVAPI_LDFLAGS="-module -avoid-version -shrext \"\$(MMSUFFIX)\""
AC_SUBST(MMDEVAPI_LDFLAGS)

MM_INSTALL_DIRS

# Micro-Manager libraries have a prefix & suffix to make them unique
case $host in
   *-*-linux*)
   MMSUFFIX=".so.0"
   MMPREFIX="libmmgr_dal_"
   ;;
esac
if test -z "$MMSUFFIX"; then
  MMSUFFIX=""
fi
if test -z "$MMPREFIX"; then
  MMPREFIX="mmgr_dal_"
fi

AC_MSG_CHECKING(library suffix)
AC_MSG_RESULT($MMSUFFIX)
AC_SUBST(MMSUFFIX)
AC_MSG_CHECKING(library prefix)
AC_MSG_RESULT($MMPREFIX)
AC_SUBST(MMPREFIX)

# Checks for library functions.
AC_CHECK_FUNCS([memset])

# This is the list of subdirectories containing a Makefile.am.
m4_define([device_adapter_dirs], [m4_strip([
    DemoCamera
    Utilities
])])
AC_CONFIG_FILES(Makefile m4_map_args_w(device_adapter_dirs, [], [/Makefile], [ ]))
AC_OUTPUT
"""


def build(dest: Path, overwrite: bool | None = None) -> None:
    """Build Micro-Manager device adapters from the git repo.

    Currently only supports Apple Silicon.
    Run on command line with `mmcore build-dev`

    Parameters
    ----------
    dest : Path
        Destination directory for the built adapters.
    overwrite : bool | None
        Whether to overwrite an existing installation. If `None`, will prompt.
    """
    if SYSTEM == "Darwin" and MACHINE == "arm64":
        return _build_macos_arm64(dest, overwrite)
    if SYSTEM == "Linux":
        return _build_linux(dest, overwrite)
    raise NotImplementedError(
        f"Building on {SYSTEM} {MACHINE} is not currently supported."
    )


def _require(command: str, link: str = "") -> None:
    if not shutil.which(command):
        print(f"{command!r} is required but not found. Please install it first. {link}")
        return


def _build_macos_arm64(dest: Path, overwrite: bool | None = None) -> None:
    _require("brew", "https://brew.sh")
    _require("git")

    for dep in ("autoconf", "automake", "libtool", "boost"):
        output = subprocess.run(["brew", "ls", "--versions", dep], capture_output=True)
        if not output.stdout:
            ok = input(f"Dependency {dep!r} is not installed. Install? [y/N] ")
            if ok.lower() in ("y", "yes"):
                subprocess.run(["brew", "install", dep], check=True)
            else:
                print("Aborting.")
                return

    env_vars = {
        "LDFLAGS": "-L/opt/homebrew/lib/ -Wl,-rpath,'$ORIGIN'",
        "CPPFLAGS": "-I/opt/homebrew/include/",
    }
    install_into(dest, overwrite, env_vars=env_vars)


def _build_linux(dest: Path, overwrite: bool | None = None) -> None:
    _require("git")

    print("sudo will required to install the following packages:")
    print(
        "  build-essential autoconf automake libtool autoconf-archive pkg-config "
        "libboost-all-dev swig3.0"
    )

    subprocess.run(["sudo", "apt-get", "update"], check=True)
    subprocess.run(
        [
            "sudo",
            "apt-get",
            "-y",
            "install",
            "build-essential",
            "autoconf",
            "automake",
            "libtool",
            "autoconf-archive",
            "pkg-config",
            "libboost-all-dev",
            "swig3.0",
        ],
        check=True,
    )

    install_into(dest, overwrite)


def install_into(
    dest: Path, overwrite: bool | None, env_vars: dict | None = None
) -> None:
    with _mm_repo_tmp_path() as repo_path:
        sub_dest = _ensure_subdir(dest, repo_path, overwrite)
        if sub_dest is None:
            return

        # update the configure.ac and Makefile.am files
        devAdapters = repo_path / "mmCoreAndDevices" / "DeviceAdapters"
        (devAdapters / "configure.ac").write_text(_MINIMAL_CONFIG)
        (devAdapters / "Makefile.am").write_text(_MINIMAL_MAKE)

        if env_vars:
            os.environ.update(env_vars)

        # make and install
        subprocess.run(["./autogen.sh"], check=True)
        subprocess.run(
            ["./configure", f"--prefix={repo_path.parent}", "--without-java"],
            check=True,
        )
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
def _mm_repo_tmp_path() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        cmd = ["git", "clone", "--recurse-submodules", MM_REPO]
        subprocess.run(cmd, cwd=tmpdir, check=True)

        repo_path = tmp_path / "micro-manager"
        os.chdir(repo_path)
        yield repo_path


def _ensure_subdir(
    dest: Path, repo_path: Path, overwrite: bool | None = None
) -> Path | None:
    # get sha to determine destination path
    cmd = ["git", "rev-parse", "--short", "HEAD"]
    sha = subprocess.check_output(cmd, cwd=repo_path)
    subdest = dest / f"Micro-Manager-{sha.decode().strip()}"

    # check if dest exists and maybe overwrite
    if subdest.exists():
        if overwrite is False:
            print(f"{subdest!r} already exists and overwrite is False. Aborting.")
            return None
        elif overwrite:
            shutil.rmtree(subdest)
        else:
            delete = Prompt.ask(
                f"{subdest!r} already exists. Delete?", choices=["y", "n"], default="n"
            )
            if delete.lower() in ("y", "yes"):
                shutil.rmtree(subdest)
            else:
                print("[red]Aborting.")
                return None
    return subdest
