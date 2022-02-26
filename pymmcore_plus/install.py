import os
import re
import shutil
import ssl
import urllib.request
from pathlib import Path
from subprocess import run

_version_regex = re.compile(r"(\d+\.){2}\d+")
VERSION = "2.0.1"
RELEASE = 20211007
DEFAULT_DEST = Path(__file__).parent

ssl._create_default_https_context = ssl._create_unverified_context


def progressBar(current, chunksize, total, barLength=40):
    percent = float(current * chunksize) * 100 / total
    arrow = "-" * int(percent / 100 * barLength - 1) + ">"
    spaces = " " * (barLength - len(arrow))
    if not os.getenv("CI"):
        print("Progress: [%s%s] %d %%" % (arrow, spaces, percent), end="\r")


def download_url(url, output_path):
    print(f"downloading {url} ...")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    urllib.request.urlretrieve(url, filename=output_path, reporthook=progressBar)


def _mac_main(dest_dir=DEFAULT_DEST, version=VERSION, release=RELEASE, noprompt=False):
    if release == "latest":
        url = "https://download.micro-manager.org/latest/macos/"
        fname = "Micro-Manager-x86_64-latest.dmg"
        dst = dest_dir / "Micro-Manager-latest_mac"
    else:
        url = "https://valelab4.ucsf.edu/~MM/builds/2.0/Mac/"
        fname = f"Micro-Manager-{version}-{release}.dmg"
        dst = dest_dir / f"{fname[:-4]}_mac"

    if dst.exists() and not noprompt:
        resp = input(f"Micro-manager already exists at\n{dst}\nOverwrite [Y/n]?")
        if resp.lower().startswith("n"):
            print("aborting")
            return

    download_url(f"{url}{fname}", fname)
    run(["hdiutil", "attach", "-nobrowse", fname], check=True)
    try:
        src = next(Path("/Volumes/Micro-Manager").glob("Micro-Manager*"))
    except StopIteration:
        src = f"/Volumes/Micro-Manager/{fname[:-4]}"
    shutil.copytree(src, dst, dirs_exist_ok=True)
    run(["hdiutil", "detach", "/Volumes/Micro-Manager"], check=True)
    os.unlink(fname)
    # fix gatekeeper ... requires password
    print(
        "\nYour password may be required to enable Micro-manager "
        "in your security settings."
        "\nNote: you can also quit now (cmd-C) and do this "
        "manually in the Security & Privacy preference pane."
    )
    cmd = ["sudo", "xattr", "-r", "-d", "com.apple.quarantine", str(dst)]
    if noprompt:
        cmd = cmd[1:]

    run(cmd, check=True)
    # # fix path randomization
    os.rename(dst / "ImageJ.app", "ImageJ.app")
    os.rename("ImageJ.app", dst / "ImageJ.app")
    return dst


def _win_main(dest_dir=DEFAULT_DEST, version=VERSION, release=RELEASE, noprompt=False):
    if release == "latest":
        url = "https://download.micro-manager.org/latest/windows/"
        fname = "MMSetup_x64_latest.exe"
        dst = dest_dir / "Micro-Manager-latest_win"
    else:
        url = f"https://valelab4.ucsf.edu/~MM/nightlyBuilds/{version}/Windows/"
        dst = dest_dir / f"Micro-Manager-{version}-{release}_win"
        fname = f"MMSetup_64bit_{version}_{release}.exe"

    if dst.exists() and not noprompt:
        resp = input(f"Micro-manager already exists at\n{dst}\nOverwrite [Y/n]?")
        if resp.lower().startswith("n"):
            print("aborting")
            return

    download_url(f"{url}{fname}", fname)
    run(
        [fname, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={dst}"],
        check=True,
    )
    os.unlink(fname)
    return dst


def install(dest_dir=DEFAULT_DEST, version=VERSION, release="latest", noprompt=False):
    prog = _win_main if os.name == "nt" else _mac_main
    out = prog(dest_dir, version, release, noprompt)
    if out:
        print("installed to", out)


def _existing_dir(string):
    path = Path(string)
    if not path.is_dir():
        raise NotADirectoryError(string)
    return path


def _version(value: str):
    if not _version_regex.match(value):
        raise ValueError(
            f"Invalid version: {value}. Must be of form x.y.z with x y and z in 0-9"
        )
    return value


def _release(value: str):
    if value.lower() == "latest":
        return "latest"
    if len(value) != 8:
        raise ValueError(f"Invalid date: {value}. Must be eight digits.")
    return int(value)


def main():
    import sys

    print(sys.argv)
    import argparse

    parser = argparse.ArgumentParser(description="MM Device adapter installer.")
    parser.add_argument(
        "-d",
        "--dest",
        default=DEFAULT_DEST,
        type=_existing_dir,
        help=f"Directory in which to install (default: {DEFAULT_DEST})",
    )

    parser.add_argument(
        "-v",
        "--version",
        metavar="VERSION",
        type=_version,
        default=VERSION,
        help="Version number. e.g. 2.0.1 - ignored if release=latest "
        f"(default: {VERSION})",
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
    install(args.dest, args.version, args.release, args.yes)


if __name__ == "__main__":
    main()
