CORE_NAME = "pymmcore_plus.CMMCorePlus"
DEFAULT_PORT = 54333
DEFAULT_HOST = "127.0.0.1"
DEFAULT_URI = f"PYRO:{CORE_NAME}@{DEFAULT_HOST}:{DEFAULT_PORT}"
VERBOSE = False


def serve():
    import argparse

    from loguru import logger
    from Pyro5 import api

    from pymmcore_plus._serialize import register_serializers
    from pymmcore_plus.server import pyroCMMCore

    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help="port")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--verbose", action="store_true", default=VERBOSE)
    args = parser.parse_args()

    if not args.verbose:
        logger.disable("pymmcore_plus")

    register_serializers()
    api.serve(
        {pyroCMMCore: CORE_NAME},
        use_ns=False,
        host=args.host,
        port=args.port,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    serve()
