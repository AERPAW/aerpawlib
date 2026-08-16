import sys

from aerpawlib._internal.zmq import proxy_cli
from aerpawlib.cli.logging_setup import setup_logging


def main() -> int:
    setup_logging()
    return proxy_cli()


if __name__ == "__main__":
    sys.exit(main())
