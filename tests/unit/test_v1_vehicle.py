"""Unit tests for aerpawlib v1 vehicle related components."""

import socket
import threading

import pytest

from aerpawlib.v1.exceptions import PortInUseError
from aerpawlib.v1.util import Coordinate
from aerpawlib.v1.vehicle import Drone, DummyVehicle, Rover
from aerpawlib.v1.vehicle.core_vehicle import _parse_udp_connection_port


class TestDummyVehicleUnit:
    """Basic unit tests for DummyVehicle (no async needed for some)."""

    def test_creates(self):
        v = DummyVehicle()
        assert v is not None

    def test_close_noop(self):
        v = DummyVehicle()
        v.close()

    def test_close_is_idempotent(self):
        v = DummyVehicle()
        v.close()
        v.close()  # Second call should not raise

    def test_close_sets_closed_flag(self):
        v = DummyVehicle()
        assert not v._closed
        v.close()
        assert v._closed

    def test_preflight_wait_noop(self):
        v = DummyVehicle()
        v._preflight_wait(should_arm=True)

    def test_preflight_wait_multiple_times(self):
        v = DummyVehicle()
        v._preflight_wait(should_arm=False)
        v._preflight_wait(should_arm=True)

    @pytest.mark.asyncio
    async def test_arm_vehicle_noop(self):
        v = DummyVehicle()
        await v._arm_vehicle()

    @pytest.mark.asyncio
    async def test_arm_vehicle_is_async(self):
        v = DummyVehicle()
        result = await v._arm_vehicle()
        assert result is None  # noop, just must not raise


class TestParseUdpConnectionPort:
    """Parse UDP connection strings used by aerpawlib/MAVSDK."""

    def test_udp_listen_all(self):
        assert _parse_udp_connection_port("udp://:14540") == ("0.0.0.0", 14540)

    def test_udp_host_port(self):
        assert _parse_udp_connection_port("udp://127.0.0.1:14550") == (
            "127.0.0.1",
            14550,
        )

    def test_udpin_listen_all(self):
        assert _parse_udp_connection_port("udpin://:14540") == ("0.0.0.0", 14540)

    def test_udpin_host_port(self):
        assert _parse_udp_connection_port("udpin://127.0.0.1:14551") == (
            "127.0.0.1",
            14551,
        )

    def test_udpin_explicit_bind(self):
        assert _parse_udp_connection_port("udpin://0.0.0.0:14540") == ("0.0.0.0", 14540)

    def test_udpin_ipv6(self):
        assert _parse_udp_connection_port("udpin://[::1]:14540") == ("::1", 14540)

    def test_udpout_returns_none(self):
        assert _parse_udp_connection_port("udpout://192.168.1.12:14550") is None

    def test_serial_returns_none(self):
        assert _parse_udp_connection_port("serial:///dev/ttyUSB0:57600") is None

    def test_tcp_returns_none(self):
        assert _parse_udp_connection_port("tcp://localhost:5760") is None


class TestPortInUse:
    """Port-in-use fails fast instead of hanging."""

    def test_udp_port_in_use_raises_immediately(self):
        """When UDP port from connection string is in use, Drone raises PortInUseError immediately."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("0.0.0.0", 0))
        except (PermissionError, OSError):
            pytest.skip("Cannot bind socket in this environment")
        port = sock.getsockname()[1]
        try:
            with pytest.raises(PortInUseError, match="already in use"):
                Drone(f"udp://:{port}")
        finally:
            sock.close()


class TestVehicleValidationUnit:
    """Unit tests for vehicle command validation (no SITL needed)."""

    @pytest.mark.asyncio
    async def test_rover_goto_validation(self):
        # __new__ only: skip __init__ / MAVSDK; validate_tolerance runs first.
        rover = Rover.__new__(Rover)
        with pytest.raises(ValueError, match="at least"):
            await Rover.goto_coordinates(rover, Coordinate(0, 0), tolerance=0.0)

    @pytest.mark.asyncio
    async def test_drone_goto_validation(self):
        drone = Drone.__new__(Drone)
        with pytest.raises(ValueError, match="at least"):
            await Drone.goto_coordinates(drone, Coordinate(0, 0), tolerance=0.0)


class TestHeartbeatMonitoring:
    """Unit tests for Vehicle heartbeat / connection-loss detection."""

    def _make_vehicle(self):
        """Return a bare Vehicle instance (no __init__ / MAVSDK)."""
        from aerpawlib.v1.vehicle.core_vehicle import Vehicle

        v = Vehicle.__new__(Vehicle)
        v._has_heartbeat = True
        v._last_heartbeat_time = 0.0
        v._verbose_logging = False
        v._verbose_log_lock = threading.Lock()
        v._verbose_logging_file_writer = None
        v._verbose_logging_last_log_time = 0.0
        v._verbose_logging_delay = 999.0
        return v

    def test_connected_true_when_heartbeat_set(self):
        v = self._make_vehicle()
        v._has_heartbeat = True
        assert v.connected is True

    def test_connected_false_when_heartbeat_cleared(self):
        v = self._make_vehicle()
        v._has_heartbeat = False
        assert v.connected is False
