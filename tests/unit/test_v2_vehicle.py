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
