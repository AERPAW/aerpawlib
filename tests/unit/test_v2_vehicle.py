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
