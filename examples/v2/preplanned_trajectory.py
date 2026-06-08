"""
preplanned_trajectory will take in a .plan file, parse it, and make the vehicle
used (must be a drone!) follow the path provided. This is a good example of how
to use the StateMachine framework, as well as the initialize_args method. This
script also contains an example of how to use the ExternalProcess tooling, in
this case by calling ping periodically (at every waypoint).

Run with:
    aerpawlib --api-version v2 --script examples/v2/preplanned_trajectory.py \
        --vehicle drone --conn udpin://127.0.0.1:14550 --file examples/v2/geofence.kml
"""

import argparse
import asyncio
import csv
import datetime
import os
import re
from pathlib import Path
from typing import TextIO

from aerpawlib.v2 import (
    Coordinate,
    Drone,
    ExternalProcess,
    StateMachine,
    Vehicle,
    at_init,
    background,
    state,
    timed_state,
)
from aerpawlib.v2.log import LogComponent, get_logger
from aerpawlib.v2.plan import read_from_plan_complete

logger = get_logger(LogComponent.ROOT)


class PreplannedTrajectory(StateMachine):
    """Execute waypoints from a .plan file with background logging and ping latency checks."""

    _waypoints: list
    _waypoint_fname: str
    _current_waypoint: int = 0

    _default_leg_speed: float = None
    _default_heading: float = None

    _sampling_delay: float
    _cur_line: int
    _csv_writer: object
    _log_file: TextIO

    def __init__(self):
        super().__init__()
        self._current_waypoint = 0
        self._pinging = False
        self._sampling = False

    def initialize_args(self, args: list[str]) -> None:
        # use an extra argument parser to read in custom script arguments
        default_file = f"GPS_DATA_{datetime.datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}.csv"

        parser = argparse.ArgumentParser()
        parser.add_argument("--file", help="Mission plan file path.", required=True)
        parser.add_argument("--ping", help="call ping coroutine", action="store_false")
        parser.add_argument("--skipoutput", help="don't dump gps data to a file", action="store_false")
        parser.add_argument("--output", help="log output file", required=False, default=default_file)
        parser.add_argument(
            "--samplerate",
            help="log sampling rate (Hz)",
            required=False,
            type=float,
            default=1.0,
        )
        parser.add_argument(
            "--default-speed",
            help="default leg speed for vehicle",
            required=False,
            default=None,
            action="store",
            dest="default_speed",
            type=float,
        )
        parser.add_argument(
            "--look-at-heading",
            help="heading to maintain while flying, if set.",
            required=False,
            default=None,
            action="store",
            dest="default_heading",
            type=float,
        )
        parsed_args = parser.parse_args(args=args)

        self._pinging = not parsed_args.ping
        self._sampling = parsed_args.skipoutput
        self._sampling_delay = 1.0 / parsed_args.samplerate
        self._waypoint_fname = parsed_args.file

        if parsed_args.default_speed is not None:
            self._default_leg_speed = parsed_args.default_speed
        if parsed_args.default_heading is not None:
            self._default_heading = parsed_args.default_heading

        if self._sampling:
            self._log_file = open(parsed_args.output, "w+")
            self._cur_line = sum(1 for _ in self._log_file) + 1
            self._csv_writer = csv.writer(self._log_file)

    _ping_regex = re.compile(r".+icmp_seq=(?P<seq>\d+).+time=(?P<time>\d\.\d+) ms")

    async def _ping_latency(self, address: str, count: int):
        """Calculate average latency to address using ExternalProcess and ping."""
        ping = ExternalProcess("ping", params=[address, "-c", str(count)])
        await ping.start()
        latencies = []
        buff = 1
        while buff:
            buff = await ping.wait_until_output(r"icmp_seq=")
            if not buff:
                break
            ping_re_match = self._ping_regex.match(buff[-1])  # last line contains useful data
            if ping_re_match:
                latencies.append(float(ping_re_match.group("time")))
                if ping_re_match.group("seq") == str(count):  # if icmp_seq shows we've sent everything
                    break
        if not latencies:
            return 0.0
        avg_latency = sum(latencies) / len(latencies)
        return avg_latency

    @at_init
    async def ping_before_running(self, _):
        # do a few pings before waiting for the drone to arm
        if self._pinging:
            avg_ping_latency = await self._ping_latency("127.0.0.1", 5)  # ping 127.0.0.1 5 times
            logger.info(f"Average ping latency: {avg_ping_latency:.2f}ms")

    def _dump_to_csv(self, vehicle: Vehicle, line_num: int, writer):
        """Continually log stats about the vehicle to a file."""
        pos = vehicle.position
        lat, lon, alt = pos.lat, pos.lon, pos.alt
        volt = vehicle.battery.voltage
        timestamp = datetime.datetime.now()
        gps = vehicle.gps
        fix, num_sat = gps.fix_type, gps.satellites_visible
        if fix < 2:
            lat, lon, alt = -999.0, -999.0, -999.0
        vel = vehicle.velocity
        attitude = vehicle.attitude
        attitude_str = "(" + ",".join(map(str, [attitude.pitch, attitude.yaw, attitude.roll])) + ")"

        writer.writerow([line_num, lon, lat, alt, attitude_str, vel, volt, timestamp, fix, num_sat])

    @background
    async def periodic_dump(self, vehicle: Vehicle):
        while True:
            if self._sampling:
                self._dump_to_csv(vehicle, self._cur_line, self._csv_writer)
                self._log_file.flush()
                os.fsync(self._log_file.fileno())
                self._cur_line += 1
            await asyncio.sleep(self._sampling_delay)

    def cleanup(self) -> None:
        if hasattr(self, "_log_file") and self._log_file:
            self._log_file.close()

    @at_init
    async def initialize_flight(self, vehicle: Vehicle):
        default_speed = 5.0 if isinstance(vehicle, Drone) else 1.0
        if self._default_leg_speed is not None:
            default_speed = self._default_leg_speed

        logger.info(f"Reading .plan file from: {self._waypoint_fname}")
        self._waypoints = read_from_plan_complete(Path(self._waypoint_fname), default_speed)
        logger.info(f"Loaded {len(self._waypoints)} waypoints")

    @state(name="take_off", first=True)
    async def take_off(self, vehicle: Vehicle):
        # take off to the alt of the first waypoint if it's a drone
        if isinstance(vehicle, Drone):
            takeoff_alt = None
            for wp in self._waypoints:
                if wp["command"] == 22:  # TAKEOFF
                    takeoff_alt = wp["pos"][2]
                    break
            if takeoff_alt is None and len(self._waypoints) > 0:
                takeoff_alt = self._waypoints[0]["pos"][2]

            if takeoff_alt is not None:
                logger.info(f"Taking off to {takeoff_alt}m")
                await vehicle.takeoff(altitude=takeoff_alt)

        # Skip all takeoff commands for both drones and rovers
        while self._current_waypoint < len(self._waypoints) and self._waypoints[self._current_waypoint]["command"] == 22:
            self._current_waypoint += 1

        return "next_waypoint"

    @state(name="next_waypoint")
    async def next_waypoint(self, vehicle: Vehicle):
        # verify we haven't reached the end of the plan
        if self._current_waypoint >= len(self._waypoints):
            return "rtl"

        logger.info(f"Navigating to waypoint {self._current_waypoint}")
        waypoint = self._waypoints[self._current_waypoint]

        if waypoint["command"] == 20:  # RTL encountered, finish routine
            return "rtl"

        # go to next waypoint
        coords = Coordinate(*waypoint["pos"])
        target_speed = waypoint["speed"]
        # Non-blocking goto
        await vehicle.goto_coordinates(coords, target_heading=self._default_heading, blocking=False)
        await asyncio.sleep(0.5)  # MAV_CMD_DO_CHANGE_SPEED race condition mitigation
        await vehicle.set_groundspeed(target_speed)
        return "in_transit"

    @state(name="in_transit")
    async def in_transit(self, vehicle: Vehicle):
        # wait for the vehicle to arrive at the next waypoint

        # measure ping latency while on the move
        if self._pinging:
            avg_ping_latency = await self._ping_latency("127.0.0.1", 5)
            logger.info(f"Average ping latency (in transit): {avg_ping_latency:.2f}ms")

        await vehicle.await_ready_to_move()
        return "at_waypoint"

    @timed_state(name="at_waypoint", duration=3)
    async def at_waypoint(self, _):
        # perform any extra functionality to be done at a waypoint, but stay
        # there for at least 3 seconds

        # ensure that we wait for some amount of time if specified in the .plan
        wait_for = self._waypoints[self._current_waypoint]["wait_for"]
        if wait_for > 0:
            await asyncio.sleep(wait_for)

        # example: measure average ping latency
        if self._pinging:
            avg_ping_latency = await self._ping_latency("127.0.0.1", 5)
            logger.info(f"Average ping latency (at waypoint): {avg_ping_latency:.2f}ms")

        # We have finished executing this waypoint, advance the index for the next loop
        self._current_waypoint += 1
        return "next_waypoint"

    @state(name="rtl")
    async def rtl(self, vehicle: Vehicle):
        # return to the take off location and stop the script
        if vehicle.home_coords:
            home_coords = Coordinate(vehicle.home_coords.lat, vehicle.home_coords.lon, vehicle.position.alt)
            await vehicle.goto_coordinates(home_coords, target_heading=self._default_heading)
        if isinstance(vehicle, Drone):
            await vehicle.land()

        logger.info("Mission done!")
