CORE_NAME = "pymmcore_remote.CMMCorePlus"
DEFAULT_PORT = 54333
DEFAULT_HOST = "127.0.0.1"
DEFAULT_URI = f"PYRO:{CORE_NAME}@{DEFAULT_HOST}:{DEFAULT_PORT}"


def main():
    import argparse

    from Pyro5.api import serve

    from pymmcore_remote._pyrocore import pyroCMMCore
    from pymmcore_remote._serialize import register_serializers

    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help="port")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--verbose", default=DEFAULT_HOST)
    args = parser.parse_args()

    register_serializers()

    serve(
        {pyroCMMCore: CORE_NAME},
        use_ns=False,
        host=args.host,
        port=args.port,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
