"""
Read in a mission plan from a specified file and execute it. This script also
will produce a log file (as specified in logging/GPSLogger/README.txt) as it
travels through the provided plan. This specific script is expecting a double
square mission. During the first square a ping test will take place. During the
second square an iperf test will take place.
Minimal usage:
    python -m aerpawlib --script guided_mission_logging --conn <connection str> \
            --file <mission plan file> --vehicle drone --destination_ip <ip>
Extra params:
    --output:       [defualt specified in GPSLogger] specific output file to use
    --samplerate:   [default 1Hz] sample rate in Hz (samples / sec)
"""

import csv
import datetime
import os
import subprocess
from argparse import ArgumentParser
from typing import TextIO

from aerpawlib.v1.runner import StateMachine, background, sleep, state, timed_state
from aerpawlib.v1.util import Coordinate, Waypoint, read_from_plan
from aerpawlib.v1.vehicle import Drone, Rover, Vehicle

WAYPOINT_WAIT_TIME = 3  # s


def _dump_to_csv(vehicle: Vehicle, line_num: int, writer):
    att = vehicle._vehicle.attitude
    pitch = att.pitch
    yaw = att.yaw
    roll = att.roll
    pos = vehicle.position
    lat, lon, alt = pos.lat, pos.lon, pos.alt
    volt = vehicle.battery.voltage
    timestamp = datetime.datetime.now()
    gps = vehicle.gps
    fix, num_sat = gps.fix_type, gps.satellites_visible
    if fix < 2:
        lat, lon, alt = -999, -999, -999
    writer.writerow([line_num, lon, lat, alt, pitch, yaw, roll, volt, timestamp, fix, num_sat])


class PreplannedTrajectoryLogging(StateMachine):
    def initialize_args(self, extra_args: list[str]):
        default_file = f"GPS_DATA_{datetime.datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}.csv"

        parser = ArgumentParser()
        parser.add_argument("--file", help="Mission plan file (path)", required=True)
        parser.add_argument("--output", help="log output file", required=False, default=default_file)
        parser.add_argument("--samplerate", help="log sampling rate (Hz)", required=False, default=1)
        parser.add_argument("--destination_ip", help="ip of server", required=True)
        args = parser.parse_args(args=extra_args)
        self._waypoints = read_from_plan(args.file)

        self._destination_ip = args.destination_ip
        self._sampling_delay = 1 / args.samplerate
        self._log_file = open(args.output, "w+")
        self._cur_line = sum(1 for _ in self._log_file) + 1
        self._csv_writer = csv.writer(self._log_file)

    _next_sample: float = 0
    _sampling_delay: float
    _cur_line: int
    _csv_writer: object
    _log_file: TextIO

    @background
    async def periodic_dump(self, vehicle: Vehicle):
        _dump_to_csv(vehicle, self._cur_line, self._csv_writer)
        self._log_file.flush()
        os.fsync(self._log_file)
        self._cur_line += 1
        await sleep(self._sampling_delay)

    def cleanup(self):
        self._log_file.close()

    _waypoints: list[Waypoint]
    _current_waypoint: int = 0

    @state(name="take_off", first=True)
    async def take_off(self, vehicle: Vehicle):
        if isinstance(vehicle, Drone):
            takeoff_alt = self._waypoints[self._current_waypoint][3]
            print(f"Taking off to {takeoff_alt}m")
            await vehicle.takeoff(takeoff_alt)
            return "next_waypoint"
        elif isinstance(vehicle, Rover):
            return "next_waypoint"
        # intentionally terminate if we're not a known vehicle
        return

    @state(name="next_waypoint")
    async def next_waypoint(self, vehicle: Vehicle):
        print(f"Waypoint {self._current_waypoint}")
        if self._current_waypoint >= len(self._waypoints):
            return "rtl"
        waypoint = self._waypoints[self._current_waypoint]
        if self._current_waypoint in [1, 10, 19]:
            print("Starting ping")
            self._ping = subprocess.Popen(
                [
                    "/home/pi/AERPAW-Dev/AHN/E-VM/Profile_software/ProfileScripts/Traffic/Samples/startPingCLArguments.sh",
                    self._destination_ip,
                ]
            )
        if self._current_waypoint in [5, 14, 23]:
            print("Terminating ping")
            subprocess.Popen(["screen", "-S", "ping", "-X", "quit"])
            self._ping.terminate()
            print("Starting iperf")
            self._iperf = subprocess.Popen(
                [
                    "/home/pi/AERPAW-Dev/AHN/E-VM/Profile_software/ProfileScripts/Traffic/Samples/startIperfClientCLArguments.sh",
                    self._destination_ip,
                    "1000",
                ]
            )
        if self._current_waypoint in [9, 18, 27]:
            print("Terminating iperf")
            subprocess.Popen(["screen", "-S", "iperfclient", "-X", "quit"])
            self._iperf.terminate()

        self._current_waypoint += 1
        if waypoint[0] == 22:  # ignore takeoff command
            return "next_waypoint"
        if waypoint[0] == 20:  # RTL encountered, finish routine
            return "rtl"
        # travel to next waypoint
        await vehicle.goto_coordinates(Coordinate(*waypoint[1:4]), tolerance=2)
        return "in_transit"

    @state(name="in_transit")
    async def in_transit(self, vehicle: Vehicle):
        await vehicle.await_ready_to_move()
        return "at_waypoint"

    @timed_state(name="at_waypoint", duration=WAYPOINT_WAIT_TIME)
    async def at_waypoint(self, _):
        return "next_waypoint"

    @state(name="rtl")
    async def rtl(self, vehicle: Vehicle):
        await vehicle.goto_coordinates(Coordinate(vehicle.home_coords.lat, vehicle.home_coords.lon, vehicle.position.alt))
        return "finish_movement"

    @state(name="finish_movement")
    async def finish_movement(self, vehicle: Vehicle):
        await vehicle.await_ready_to_move()
        if isinstance(vehicle, Drone):
            print("Landing!")
            await vehicle.land()
            return "wait_for_disarm"
        elif isinstance(vehicle, Rover):
            await vehicle.set_armed(False)
            print("done!")
            return

    @state(name="wait_for_disarm")
    async def wait_for_disarm(self, drone: Vehicle):
        if not drone.armed:
            print("done!")
            return
        return "wait_for_disarm"
