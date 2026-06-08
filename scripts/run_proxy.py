#!/usr/bin/env python3
"""
Run the aerpawlib ZMQ proxy server.
"""

import argparse
import importlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the aerpawlib ZMQ proxy server")
    parser.add_argument(
        "--api-version",
        default="v2",
        choices=["v1", "v2"],
        help="API version to run the proxy for (default: v2)",
    )
    args = parser.parse_args()

    api_version = args.api_version
    try:
        api_module = importlib.import_module(f"aerpawlib.{api_version}")
        if hasattr(api_module, "run_zmq_proxy"):
            print(f"Starting ZMQ proxy mode for {api_version}...")
            api_module.run_zmq_proxy()
        else:
            print(f"Error: API {api_version} does not support ZMQ proxy", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: Failed to import aerpawlib {api_version}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
