import os
import shutil
import ssl
import urllib.request
from pathlib import Path
from subprocess import run

RELEASE = 20210518 if os.name == "nt" else 20210527
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


def _mac_main(dest_dir=DEFAULT_DEST, release=RELEASE):
    url = "https://valelab4.ucsf.edu/~MM/nightlyBuilds/2.0.0-gamma/Mac/"
    fname = f"Micro-Manager-2.0.0-gamma1-{release}.dmg"
    dst = dest_dir / f"{fname[:-4]}_mac"

    if dst.exists():
        resp = input(f"Micro-manager already exists at\n{dst}\nOverwrite [Y/n]?")
        if resp.lower().startswith("n"):
            print("aborting")
            return

    download_url(f"{url}{fname}", fname)
    run(["hdiutil", "attach", "-nobrowse", fname], check=True)
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
    run(["sudo", "xattr", "-r", "-d", "com.apple.quarantine", str(dst)], check=True)
    # # fix path randomization
    os.rename(dst / "ImageJ.app", "ImageJ.app")
    os.rename("ImageJ.app", dst / "ImageJ.app")
    return dst


def _win_main(dest_dir=DEFAULT_DEST, release=RELEASE):
    url = "https://valelab4.ucsf.edu/~MM/nightlyBuilds/2.0.0-gamma/Windows/"
    fname = f"MMSetup_64bit_2.0.0-gamma1_{release}.exe"
    dst = dest_dir / f"Micro-Manager-2.0.0-gamma1-{release}_win"

    if dst.exists():
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


def install(dest_dir=DEFAULT_DEST):
    out = _win_main(dest_dir) if os.name == "nt" else _mac_main(dest_dir)
    if out:
        print("installed to", out)


def _existing_dir(string):
    path = Path(string)
    if not path.is_dir():
        raise NotADirectoryError(string)
    return path


def _dateint(value):
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
        "-r",
        "--release",
        metavar="DATE",
        type=_dateint,
        default=RELEASE,
        help="8 digit date (YYYYMMDD) of MM nightly build to fetch "
        f"(default: {RELEASE})",
    )

    args = parser.parse_args()
    install(args.dest)


if __name__ == "__main__":
    main()
