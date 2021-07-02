import os
import shutil
import ssl
import urllib.request
from pathlib import Path
from subprocess import run

MAC_RELEASE = 20210527
WIN_RELEASE = 20210518

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


def mac_main(release=MAC_RELEASE):
    url = "https://valelab4.ucsf.edu/~MM/nightlyBuilds/2.0.0-gamma/Mac/"
    fname = f"Micro-Manager-2.0.0-gamma1-{release}.dmg"
    dst = Path(__file__).parent / f"{fname[:-4]}_mac"

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
        "\nYour password is required to enable Micro-manager in your security settings."
        "\nNote: you can also quit now (cmd-C) and do this "
        "manually in the Security & Privacy preference pane."
    )
    run(["sudo", "xattr", "-r", "-d", "com.apple.quarantine", str(dst)], check=True)
    # # fix path randomization
    os.rename(dst / "ImageJ.app", "ImageJ.app")
    os.rename("ImageJ.app", dst / "ImageJ.app")
    return dst


def win_main(release=WIN_RELEASE):
    url = "https://valelab4.ucsf.edu/~MM/nightlyBuilds/2.0.0-gamma/Windows/"
    fname = f"MMSetup_64bit_2.0.0-gamma1_{release}.exe"
    dst = Path(__file__).parent / f"Micro-Manager-2.0.0-gamma1-{release}_win"

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


def install():
    print("installing device drivers")
    dest = win_main() if os.name == "nt" else mac_main()
    if dest:
        print("installed to", dest)


if __name__ == "__main__":
    install()
