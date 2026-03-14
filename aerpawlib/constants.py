"""Shared top-level constants for CLI.

These constants are API-version agnostic and used by ``aerpawlib.__main__``.
"""

# Polling interval while waiting for v1 vehicle objects to report connected.
# Keep this modest to avoid busy-waiting while still reacting quickly.
VEHICLE_CONNECT_POLL_INTERVAL_S = 0.1

# Polling interval used by the CLI-side v1 connection-loss watcher.
# This drives fail-fast responsiveness when ``vehicle.connected`` drops.
RUNNER_DISCONNECT_POLL_INTERVAL_S = 0.1

# Default timeout used by the CLI for initial vehicle connection attempts.
DEFAULT_CONNECTION_TIMEOUT_S = 30.0

# Default timeout used by the CLI for heartbeat/disconnect fail-fast checks.
DEFAULT_HEARTBEAT_TIMEOUT_S = 5.0

# Default gRPC port passed to embedded MAVSDK server processes.
DEFAULT_MAVSDK_PORT = 50051

# Default safety-checker port used when connected to AERPAW in v2.
DEFAULT_SAFETY_CHECKER_PORT = 14580
