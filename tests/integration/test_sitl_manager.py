"""
Tests for the SITL Manager itself.
"""
import pytest
import os
import time

pytestmark = pytest.mark.integration


class TestSITLManager:
    """Tests for SITLManager class."""

    def test_sitl_manager_import(self):
        """Test SITLManager can be imported."""
        from aerpawlib.sitl import SITLManager
        assert SITLManager is not None

    def test_sitl_manager_creation(self):
        """Test SITLManager can be created."""
        from aerpawlib.sitl import SITLManager
        manager = SITLManager()
        assert manager is not None
        assert manager.instance == 0

    def test_sitl_manager_custom_args(self):
        """Test SITLManager with custom args."""
        from aerpawlib.sitl import SITLManager
        manager = SITLManager("-v copter --speedup 10")
        assert "-v copter" in manager.args
        assert "--speedup 10" in manager.args

    def test_sitl_manager_instance_parsing(self):
        """Test SITLManager parses instance from args."""
        from aerpawlib.sitl import SITLManager

        manager0 = SITLManager("-v copter -I 0")
        assert manager0.instance == 0

        manager1 = SITLManager("-v copter -I 1")
        assert manager1.instance == 1

        manager2 = SITLManager("-v copter --instance 2")
        assert manager2.instance == 2

    def test_sitl_manager_port_calculation(self):
        """Test port calculation for different instances."""
        from aerpawlib.sitl import SITLManager

        manager0 = SITLManager("-v copter -I 0")
        manager1 = SITLManager("-v copter -I 1")

        # Instance 0 should have base ports
        assert manager0.udp_port == 14550

        # Instance 1 should have offset ports
        assert manager1.udp_port == 14551

    def test_sitl_manager_connection_string(self):
        """Test connection string format."""
        from aerpawlib.sitl import SITLManager

        manager = SITLManager()
        conn = manager.connection_string

        assert "udpin://" in conn
        assert "127.0.0.1" in conn
        assert str(manager.udp_port) in conn


class TestSITLAvailability:
    """Tests for SITL availability detection."""

    def test_find_ardupilot_path(self):
        """Test ArduPilot path detection."""
        from aerpawlib.sitl import SITLManager

        manager = SITLManager()
        # Should either find a path or return None
        path = manager.ardupilot_path
        if path is not None:
            assert os.path.exists(path)

    def test_find_sim_vehicle(self):
        """Test sim_vehicle.py detection."""
        from aerpawlib.sitl import SITLManager

        manager = SITLManager()
        sim_vehicle = manager._find_sim_vehicle()

        # If found, should be a valid path
        if sim_vehicle is not None:
            assert os.path.exists(sim_vehicle)
            assert "sim_vehicle.py" in sim_vehicle


@pytest.mark.slow
class TestSITLStartStop:
    """Tests for SITL start/stop (slow tests)."""

    def test_sitl_start_stop(self):
        """Test SITL starts and stops cleanly."""
        from aerpawlib.sitl import SITLManager

        manager = SITLManager("-v copter -w --no-mavproxy --speedup 10")

        # Check if SITL is available
        if manager._find_sim_vehicle() is None:
            pytest.skip("SITL not available")

        try:
            conn_string = manager.start(timeout=180)
            assert manager.is_running is True
            assert conn_string == manager.connection_string
        finally:
            manager.stop()
            time.sleep(2)
            assert manager.is_running is False

    def test_sitl_context_manager(self):
        """Test SITL works as context manager."""
        from aerpawlib.sitl import SITLManager

        manager = SITLManager("-v copter -w --no-mavproxy --speedup 10")

        if manager._find_sim_vehicle() is None:
            pytest.skip("SITL not available")

        with manager as sitl:
            assert sitl.is_running is True

        time.sleep(2)
        assert manager.is_running is False

