from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from psutil import Process
CORE_NAME = "pymmcore_plus.CMMCorePlus"
DEFAULT_PORT = 54333
DEFAULT_HOST = "127.0.0.1"
DEFAULT_URI = f"PYRO:{CORE_NAME}@{DEFAULT_HOST}:{DEFAULT_PORT}"
VERBOSE = False


def _get_remote_pid(host, port) -> Optional["Process"]:
    import psutil

    for proc in psutil.process_iter(["connections"]):
        for pconn in proc.info["connections"] or []:
            if pconn.laddr.port == port and pconn.laddr.ip == host:
                return proc
    return None


def try_kill_server(host: str = None, port: int = None):
    from loguru import logger

    if host is None:
        host = DEFAULT_HOST
    if port is None:
        port = DEFAULT_PORT

    proc = _get_remote_pid(host, port)
    if proc is not None:
        proc.kill()
        logger.info(f"Killed process on {host=}:{port=}")
    else:
        logger.info("No process found")


def serve():
    import argparse

    import Pyro5
    from loguru import logger

    from pymmcore_plus.remote._serialize import register_serializers
    from pymmcore_plus.remote.server import pyroCMMCore

    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help="port")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--verbose", action="store_true", default=VERBOSE)
    args = parser.parse_args()

    if not args.verbose:
        logger.disable("pymmcore_plus")

    register_serializers()
    Pyro5.api.serve(
        {pyroCMMCore: CORE_NAME},
        use_ns=False,
        host=args.host,
        port=args.port,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    serve()
