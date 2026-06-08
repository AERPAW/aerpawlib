"""
ZMQ Runner Example (Leader) - modern v2 API

This script demonstrates multi-vehicle coordination using ZMQ.
The leader drone measures ping latency and transitions the follower drone.

Run with:
    aerpawlib --run-proxy  # Run in separate terminal first

    aerpawlib --api-version v2 --script examples/v2/zmq_runner/leader.py \
        --conn udpin://127.0.0.1:14550 --vehicle drone \
        --zmq-identifier leader --zmq-proxy-server 127.0.0.1
"""

import asyncio
import re

from aerpawlib.v2 import ExternalProcess, ZmqStateMachine, state

target_ip = "127.0.0.1"


class LeaderRunner(ZmqStateMachine):
    """ZMQ StateMachine leader runner."""

    _ping_regex = re.compile(r".+icmp_seq=(?P<seq>\d+).+time=(?P<time>\d+(?:\.\d+)?) ms")

    async def _ping_latency(self, address: str, count: int):
        """Calculate average latency to address using ExternalProcess and ping."""
        ping = ExternalProcess("ping", params=["-c", str(count), address])
        await ping.start()
        latencies = []
        buff = 1
        while buff:
            buff = await ping.wait_until_output(r"icmp_seq=")
            if not buff:
                break
            ping_re_match = self._ping_regex.match(buff[-1])
            if ping_re_match is None:
                continue
            latencies.append(float(ping_re_match.group("time")))
            if ping_re_match.group("seq") == str(count):
                break
        if not latencies:
            raise RuntimeError(
                f"Ping to {address} produced no parseable output (process may have exited early)",
            )
        return sum(latencies) / len(latencies)

    @state(name="launch", first=True)
    async def state_start(self, _):
        print("[leader] waiting to start")
        await asyncio.sleep(10)
        return "start_ping"

    @state(name="start_ping")
    async def state_start_ping(self, _):
        p = await self._ping_latency(target_ip, 5)
        print(f"[leader] ping_result: {p:.2f}ms")
        await self.transition_runner("follower", "takeoff")
        return "wait_for_waypoint"

    @state(name="wait_for_waypoint")
    async def state_wait_waypoint(self, _):
        return "wait_for_waypoint"

    @state(name="waypoint_ping")
    async def state_ping_waypoint(self, _):
        p = await self._ping_latency(target_ip, 5)
        print(f"[leader] ping_result: {p:.2f}ms")
        await self.transition_runner("follower", "rtl")
        return "wait_for_rtl"

    @state(name="wait_for_rtl")
    async def state_wait_rtl(self, _):
        return "wait_for_rtl"

    @state(name="last_ping")
    async def state_last_ping(self, _):
        p = await self._ping_latency(target_ip, 5)
        print(f"[leader] ping_result: {p:.2f}ms")
        await self.transition_runner("follower", "land")
        return
