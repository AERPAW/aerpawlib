# leader script

import re

from aerpawlib.v1.runner import (
    ZmqStateMachine,
    at_init,
    background,
    in_background,
    sleep,
    state,
    timed_state,
)
from aerpawlib.v1.util import Coordinate, Waypoint, read_from_plan_complete
from aerpawlib.v1.vehicle import Drone

from aerpawlib.v1.external import ExternalProcess

target_ip = "127.0.0.1"


class LeaderRunner(ZmqStateMachine):
    _ping_regex = re.compile(
        r".+icmp_seq=(?P<seq>\d+).+time=(?P<time>\d\.\d+) ms"
    )

    async def _ping_latency(self, address: str, count: int):
        """
        This function will calculate the average latency to `address` by using
        ping and looking at the time in the output. This makes use of native
        aerpawlib tooling (ExternalProcess)
        """
        ping = ExternalProcess("ping", params=["-c", str(count), address])
        await ping.start()
        latencies = []
        # repeatedly wait for ping to produce output w/ icmp_seq field
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
                f"Ping to {address} produced no parseable output (process may have exited early)"
            )
        return sum(latencies) / len(latencies)

    @state(name="launch", first=True)
    async def state_start(self, _):
        print("waiting to start")
        await sleep(10)
        return "start_ping"

    @state(name="start_ping")
    async def state_start_ping(self, _):
        p = await self._ping_latency(target_ip, 5)
        print(f"ping_result: {p}")
        await self.transition_runner("follower", "takeoff")
        return "wait_for_waypoint"

    @state(name="wait_for_waypoint")
    async def state_wait_waypoint(self, _):
        return "wait_for_waypoint"

    @state(name="waypoint_ping")
    async def state_ping_waypoint(self, _):
        p = await self._ping_latency(target_ip, 5)
        print(f"ping_result: {p}")

        await self.transition_runner("follower", "rtl")

        return "wait_for_rtl"

    @state(name="wait_for_rtl")
    async def state_wait_rtl(self, _):
        return "wait_for_rtl"

    @state(name="last_ping")
    async def state_last_ping(self, _):
        p = await self._ping_latency(target_ip, 5)
        print(f"ping_result: {p}")
        await self.transition_runner("follower", "land")
        return
