"""Clone the micro-manager source code from GitHub and build dev devices."""
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from rich import print
from rich.prompt import Prompt

# DemoCamera and Utilities are currently hard coded in here, but could
# be made configurable in the future.
_MINIMAL_MAKE = r"""
AUTOMAKE_OPTIONS = foreign
ACLOCAL_AMFLAGS = -I ../m4
SUBDIRS = DemoCamera Utilities
"""

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
micromanager_cpp_path=${ac_pwd}/..
micromanager_path=${micromanager_cpp_path}/..
MMDEVAPI_CXXFLAGS="-I${micromanager_cpp_path}/MMDevice ${BOOST_CPPFLAGS}"
AC_SUBST(MMDEVAPI_CXXFLAGS)
MMDEVAPI_LIBADD="${micromanager_cpp_path}/MMDevice/libMMDevice.la"
AC_SUBST(MMDEVAPI_LIBADD)
MMDEVAPI_LDFLAGS="-module -avoid-version -shrext \"\$(MMSUFFIX)\""
AC_SUBST(MMDEVAPI_LDFLAGS)

MM_INSTALL_DIRS

AC_MSG_CHECKING(library suffix)
AC_MSG_RESULT($MMSUFFIX)
AC_SUBST(MMSUFFIX)
AC_MSG_CHECKING(library prefix)
AC_MSG_RESULT($MMPREFIX)
AC_SUBST(MMPREFIX)
AC_CHECK_FUNCS([memset])
m4_define([device_adapter_dirs], [m4_strip([
    DemoCamera
    Utilities
])])
AC_CONFIG_FILES(Makefile m4_map_args_w(device_adapter_dirs, [], [/Makefile], [ ]))
AC_OUTPUT
"""

MM_REPO = "https://github.com/micro-manager/micro-manager.git"


def build(dest: Path, repo: str = MM_REPO, overwrite: bool | None = None) -> None:
    """Build Micro-Manager device adapters from the git repo.

    Currently only supports Apple Silicon.
    Run on command line with `mmcore build-dev`

    Parameters
    ----------
    dest : Path
        Destination directory for the built adapters.
    repo : str
        URL of the Micro-Manager git repo.
    overwrite : bool | None
        Whether to overwrite an existing installation. If `None`, will prompt.
    """
    if not (platform.system() == "Darwin" and platform.machine() == "arm64"):
        print("Sorry, only Apple Silicon is supported at this time.")
        return

    if not shutil.which("brew"):
        print("Homebrew is required but not found. Please install it: https://brew.sh")
        return

    if not shutil.which("git"):
        print("git is required but not found. Please install it first.")
        return

    for dep in ("autoconf", "automake", "libtool", "boost"):
        output = subprocess.run(["brew", "ls", "--versions", dep], capture_output=True)
        if not output.stdout:
            ok = input(f"Dependency {dep!r} is not installed. Install? [y/N] ")
            if ok.lower() in ("y", "yes"):
                subprocess.run(["brew", "install", dep], check=True)
            else:
                print("Aborting.")
                return

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        cmd = ["git", "clone", "--recurse-submodules", repo]
        subprocess.run(cmd, cwd=tmpdir, check=True)

        repo_path = tmp_path / "micro-manager"
        devAdapters = repo_path / "mmCoreAndDevices" / "DeviceAdapters"
        os.chdir(repo_path)

        # get sha to determine destination path
        cmd = ["git", "rev-parse", "--short", "HEAD"]
        sha = subprocess.check_output(cmd, cwd=repo_path)
        dest = dest / f"Micro-Manager-{sha.decode().strip()}"

        # check if dest exists and maybe overwrite
        if dest.exists():
            if overwrite is False:
                print(f"{dest!r} already exists and overwrite is False. Aborting.")
                return
            elif overwrite:
                shutil.rmtree(dest)
            else:
                delete = Prompt.ask(
                    f"{dest!r} already exists. Delete?", choices=["y", "n"], default="n"
                )
                if delete.lower() in ("y", "yes"):
                    shutil.rmtree(dest)
                else:
                    print("[red]Aborting.")
                    return

        # update the configure.ac and Makefile.am files
        (devAdapters / "configure.ac").write_text(_MINIMAL_CONFIG)
        (devAdapters / "Makefile.am").write_text(_MINIMAL_MAKE)

        # add homebrew paths to env vars
        os.environ["LDFLAGS"] = "-L/opt/homebrew/lib/ -Wl,-rpath,'$ORIGIN'"
        os.environ["CPPFLAGS"] = "-I/opt/homebrew/include/"

        # make and install
        subprocess.run(["./autogen.sh"], check=True)
        subprocess.run(["./configure", f"--prefix={tmpdir}"], check=True)
        subprocess.run(["make"], check=True)
        subprocess.run(["make", "install"], check=True)

        # copy the built adapters to the destination
        built_libs = tmp_path / "lib" / "micro-manager"
        shutil.copytree(built_libs, dest)

        # grab the demo config file to dest
        demo_cfg = repo_path / "bindist" / "any-platform" / "MMConfig_demo.cfg"
        shutil.copy(demo_cfg, dest)

    print(f":sparkles: [bold green]Installed to {dest}[/bold green] :sparkles:")
