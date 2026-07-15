import sys

from aerpawlib.cli.logging_setup import setup_logging
from aerpawlib.v2.zmqutil import run_zmq_proxy


def main() -> int:
    setup_logging()
    try:
        run_zmq_proxy()
    except Exception as e:
        print(f"Error: ZMQ proxy failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
