"""Unit tests for aerpawlib v2 vehicle connection contract."""

import asyncio

import pytest

from aerpawlib.v2.exceptions import HeartbeatLostError
from aerpawlib.v2.vehicle.base import DummyVehicle
from aerpawlib.v2.vehicle.connection_state import ConnectionState


class TestConnectionState:
    def test_connected_requires_link_and_not_closed(self):
        cs = ConnectionState(link_alive=True, closed=False)
        assert cs.connected is True
        cs.closed = True
        assert cs.connected is False

    def test_mark_closed_clears_link(self):
        cs = ConnectionState(link_alive=True)
        cs.mark_closed()
        assert cs.closed is True
        assert cs.link_alive is False
        assert cs.connected is False

    @pytest.mark.asyncio
    async def test_watch_disconnect_fires_on_stale_telemetry(self):
        cs = ConnectionState(link_alive=True)
        cs.last_telemetry_at = 0.0
        fut = cs.watch_disconnect(0.05, start_delay=0.0, check_interval=0.02)
        done, _ = await asyncio.wait([fut], timeout=2.0)
        assert fut in done
        assert isinstance(fut.exception(), HeartbeatLostError)

    @pytest.mark.asyncio
    async def test_mark_closed_cancels_watch(self):
        cs = ConnectionState(link_alive=True)
        fut = cs.watch_disconnect(60.0, start_delay=0.0)
        cs.mark_closed()
        await asyncio.sleep(0.05)
        assert fut.cancelled() or not fut.done()


class TestPortInUse:
    @pytest.mark.asyncio
    async def test_udp_port_in_use_raises(self):
        import socket

        from aerpawlib.v2.exceptions import PortInUseError
        from aerpawlib.v2.vehicle.base import Vehicle

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("0.0.0.0", 0))
        except (PermissionError, OSError):
            pytest.skip("Cannot bind socket in this environment")
        port = sock.getsockname()[1]
        try:
            with pytest.raises(PortInUseError, match="already in use"):
                await Vehicle.connect(f"udpin://0.0.0.0:{port}", timeout=2)
        finally:
            sock.close()


class TestDisarmGuard:
    def test_ground_disarm_is_not_airborne(self):
        v = DummyVehicle()
        v._state.update_position(0.0, 0.0, 0.2, 0.2)
        assert v._is_airborne_for_disarm_guard() is False
        v._state.update_position(0.0, 0.0, 5.0, 5.0)
        assert v._is_airborne_for_disarm_guard() is True


class TestDummyVehicleContract:
    def test_connected_and_closed(self):
        v = DummyVehicle()
        assert v.connected is True
        assert v.closed is False
        v.close()
        assert v.connected is False
        assert v.closed is True

    @pytest.mark.asyncio
    async def test_watch_disconnect_noop_future(self):
        v = DummyVehicle()
        fut = v.watch_disconnect(0.1)
        assert fut is not None
        v.close()

    @pytest.mark.asyncio
    async def test_aclose_cancels_and_awaits_tasks(self):
        v = DummyVehicle()

        async def slow_task() -> None:
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(slow_task())
        v._telemetry_tasks.append(task)
        await v.aclose()
        assert v.closed
        assert task.done()
        assert len(v._telemetry_tasks) == 0


class TestConnectionNormalization:
    def test_udp_normalized_to_udpin(self):
        from unittest.mock import MagicMock

        from aerpawlib.v2.vehicle.base import Vehicle

        mock_system = MagicMock()
        v = Vehicle(mock_system, "udp://127.0.0.1:14550")
        assert v._connection_string == "udpin://127.0.0.1:14550"

        v2 = Vehicle(mock_system, "UDP://:14540")
        assert v2._connection_string == "udpin://:14540"

        v3 = Vehicle(mock_system, "udpin://127.0.0.1:14550")
        assert v3._connection_string == "udpin://127.0.0.1:14550"

        v4 = Vehicle(mock_system, "tcp://127.0.0.1:5760")
        assert v4._connection_string == "tcp://127.0.0.1:5760"


class TestGuidedModeAerpaw:
    def _drone(self, *, mode: str, in_aerpaw: bool, forwarder: bool = False):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock

        from aerpawlib.v2.vehicle.drone import Drone

        system = MagicMock()
        system.action.hold = AsyncMock()
        system.mavlink_direct.send_message = AsyncMock()
        platform = SimpleNamespace(is_connected=True) if in_aerpaw else None
        drone = Drone(system, "udpin://127.0.0.1:14550", aerpaw_platform=platform)
        drone._state.update_mode(mode)
        drone._aerpaw_forwarder_reachable_cache = forwarder
        return drone

    def test_hold_is_not_already_guided_on_aerpaw(self):
        drone = self._drone(mode="HOLD", in_aerpaw=True)
        assert drone._already_in_guided_mode() is False
        assert drone._must_avoid_loiter() is True

    def test_hold_is_already_guided_on_sitl(self):
        drone = self._drone(mode="HOLD", in_aerpaw=False, forwarder=False)
        assert drone._already_in_guided_mode() is True
        assert drone._must_avoid_loiter() is False

    def test_guided_is_already_good_on_aerpaw(self):
        drone = self._drone(mode="GUIDED", in_aerpaw=True)
        assert drone._already_in_guided_mode() is True

    def test_forwarder_reachable_skips_hold_without_platform(self):
        drone = self._drone(mode="HOLD", in_aerpaw=False, forwarder=True)
        assert drone._must_avoid_loiter() is True
        assert drone._already_in_guided_mode() is False

    @pytest.mark.asyncio
    async def test_set_guided_from_hold_sends_guided_on_aerpaw(self, monkeypatch):
        drone = self._drone(mode="HOLD", in_aerpaw=True)

        async def _send(_msg):
            drone._state.update_mode("GUIDED")

        drone._system.mavlink_direct.send_message.side_effect = _send
        monkeypatch.setattr(
            "aerpawlib._internal.mavlink_ids.resolve_mav_sysid",
            lambda _s: 1,
        )
        monkeypatch.setattr(
            "aerpawlib._internal.mavlink_ids.make_set_mode_message",
            lambda *_a, **_k: object(),
        )
        await drone._set_guided_mode()
        drone._system.action.hold.assert_not_awaited()
        drone._system.mavlink_direct.send_message.assert_awaited()
        assert drone.mode == "GUIDED"

    @pytest.mark.asyncio
    async def test_set_guided_calls_hold_on_sitl(self):
        drone = self._drone(mode="STABILIZE", in_aerpaw=False, forwarder=False)

        async def _hold():
            drone._state.update_mode("HOLD")

        drone._system.action.hold.side_effect = _hold
        await drone._set_guided_mode()
        drone._system.action.hold.assert_awaited()
        drone._system.mavlink_direct.send_message.assert_not_awaited()

    def test_forwarder_not_probed_without_aerpaw_env(self, monkeypatch):
        from aerpawlib.v2.vehicle.base import DummyVehicle

        monkeypatch.delenv("AP_EXPENV_EXP_NUM", raising=False)
        monkeypatch.delenv("AP_EXPENV_THIS_CONTAINER_EXP_NODE_NUM", raising=False)
        called = []
        monkeypatch.setattr(
            "aerpawlib._internal.aerpaw_ping.ping_forward_server",
            lambda *_a, **_k: called.append(True) or True,
        )
        v = DummyVehicle()
        v._aerpaw_forwarder_reachable_cache = None
        assert v._aerpaw_forwarder_reachable() is False
        assert called == []
