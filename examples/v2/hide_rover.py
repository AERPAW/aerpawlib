"""
hide_rover will make the vehicle used (a rover)
take in a .plan file and .kml file (geofence), parse them,
and make the vehicle follow the path provided in the plan.
After finishing the path, the rover will move to a random coordinate
within the provided geofence and "hide". The .plan file should move the rover
to a location it can move to anywhere inside the geofence safely.
You can optionally provide a specific latitude & longitude to
hide the rover at via arguments (see Usage).

Run with:
    aerpawlib --api-version v2 --script examples/v2/hide_rover.py \
        --vehicle rover --conn udpin://127.0.0.1:14550 \
        --file examples/v2/plan_example.py \
        --hide-fence examples/v2/geofence.kml
"""

import argparse
import asyncio
import csv
import datetime
import os
import random
from pathlib import Path
from typing import ClassVar, TextIO

from aerpawlib.v2 import (
    Coordinate,
    StateMachine,
    Vehicle,
    background,
    state,
    timed_state,
)
from aerpawlib.v2.geofence import inside, read_geofence
from aerpawlib.v2.log import LogComponent, get_logger
from aerpawlib.v2.plan import read_from_plan_complete

logger = get_logger(LogComponent.ROOT)


class HideRover(StateMachine):
    """Rover mission that follows waypoints and then hides at a coordinate within a geofence."""

    _waypoints: ClassVar[list] = []
    _waypoint_fname: str
    _current_waypoint: int = 0

    _default_leg_speed: float = None
    _default_heading: float = None
    _hide_latitude: float = None
    _hide_longitude: float = None

    _sampling_delay: float
    _cur_line: int
    _csv_writer: object
    _log_file: TextIO
    _hide_geofence: list

    def __init__(self):
        super().__init__()
        self._current_waypoint = 0
        self._sampling = False

    def initialize_args(self, args: list[str]) -> None:
        # use an extra argument parser to read in custom script arguments
        default_file = f"GPS_DATA_{datetime.datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}.csv"

        parser = argparse.ArgumentParser()
        parser.add_argument("--file", help="Mission plan file path.", required=True)
        parser.add_argument(
            "--skipoutput",
            help="don't dump gps data to a file",
            action="store_false",
        )
        parser.add_argument(
            "--output",
            help="log output file",
            required=False,
            default=default_file,
        )
        parser.add_argument(
            "--samplerate",
            help="log sampling rate (Hz)",
            required=False,
            default=1.0,
            type=float,
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
            "--lat",
            type=float,
            help="latitude to hide rover at",
            required=False,
            default=None,
            action="store",
            dest="latitude",
        )
        parser.add_argument(
            "--lon",
            type=float,
            help="longitude to hide rover at",
            required=False,
            default=None,
            action="store",
            dest="longitude",
        )
        parser.add_argument(
            "--hide-fence",
            type=str,
            help="geofence to hide the rover in",
            required=True,
            default=None,
            action="store",
            dest="geofence_file_name",
        )
        parsed_args = parser.parse_args(args=args)

        self._sampling = parsed_args.skipoutput
        self._sampling_delay = 1.0 / parsed_args.samplerate
        self._waypoint_fname = parsed_args.file
        self._hide_geofence = read_geofence(parsed_args.geofence_file_name)

        if parsed_args.default_speed is not None:
            self._default_leg_speed = parsed_args.default_speed
        if parsed_args.latitude is not None:
            self._hide_latitude = parsed_args.latitude
        if parsed_args.longitude is not None:
            self._hide_longitude = parsed_args.longitude

        if self._sampling:
            self._log_file = open(parsed_args.output, "w+")
            self._cur_line = sum(1 for _ in self._log_file) + 1
            self._csv_writer = csv.writer(self._log_file)

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
        writer.writerow(
            [
                line_num,
                lon,
                lat,
                alt,
                attitude_str,
                vel,
                volt,
                timestamp,
                fix,
                num_sat,
            ],
        )

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

    def generate_random_coordinate(self, geofence: list):
        """Generates a random coordinate within the provided geofence."""
        min_lat, max_lat, min_lon, max_lon = (
            geofence[0]["lat"],
            geofence[0]["lat"],
            geofence[0]["lon"],
            geofence[0]["lon"],
        )
        for coord in geofence:
            min_lat = min(min_lat, coord["lat"])
            max_lat = max(max_lat, coord["lat"])
            min_lon = min(min_lon, coord["lon"])
            max_lon = max(max_lon, coord["lon"])

        random_lat, random_lon = (
            random.uniform(min_lat, max_lat),
            random.uniform(min_lon, max_lon),
        )
        while not inside(random_lon, random_lat, geofence):
            random_lat, random_lon = (
                random.uniform(min_lat, max_lat),
                random.uniform(min_lon, max_lon),
            )

        return Coordinate(random_lat, random_lon)

    @state(name="init_state", first=True)
    async def initialize(self):
        # initialize parameters needed for running and read waypoints from plan
        default_speed = 1.0
        if self._default_leg_speed is not None:
            default_speed = self._default_leg_speed

        self._waypoints = read_from_plan_complete(Path(self._waypoint_fname), default_speed)

        # check if hide_latitude and hide_longitude are inside geofence if specified via
        # arguments
        if (
            self._hide_latitude is not None
            and self._hide_longitude is not None
            and not inside(
                self._hide_longitude,
                self._hide_latitude,
                self._hide_geofence,
            )
        ):
            logger.warning(
                "Specified latitude, longitude not inside provided geofence.",
            )

        # checks if only one coordinate was specified via arguments (this is invalid, so
        # the script will stop)
        if (self._hide_latitude is None) ^ (self._hide_longitude is None):
            logger.error(
                "Only one coordinate unit was specified (either latitude or longitude). Please specify either both or neither.\nStopping script",
            )
            return None

        # generate random hide coords if not specified
        if self._hide_latitude is None and self._hide_longitude is None:
            random_coord = self.generate_random_coordinate(self._hide_geofence)
            self._hide_latitude = random_coord.lat
            self._hide_longitude = random_coord.lon

        logger.info(f"Hiding at Latitude: {self._hide_latitude}")
        logger.info(f"Hiding at Longitude: {self._hide_longitude}")

        return "next_waypoint"

    @state(name="next_waypoint")
    async def next_waypoint(self, vehicle: Vehicle):
        # figure out the next waypoint to go to
        self._current_waypoint += 1
        # if last waypoint has been reached, transition to hide_rover state
        if self._current_waypoint >= len(self._waypoints):
            return "hide_rover"
        logger.info(f"Waypoint {self._current_waypoint}")
        waypoint = self._waypoints[self._current_waypoint]

        # go to next waypoint
        coords = Coordinate(*waypoint["pos"])
        target_speed = waypoint["speed"]
        await vehicle.set_groundspeed(target_speed)
        await vehicle.goto_coordinates(coords, target_heading=self._default_heading, blocking=False)
        return "in_transit"

    @state(name="in_transit")
    async def in_transit(self, vehicle: Vehicle):
        # wait for the vehicle to arrive at the next waypoint and then transition
        await vehicle.await_ready_to_move()
        return "at_waypoint"

    @timed_state(name="at_waypoint", duration=3)
    async def at_waypoint(self, _):
        # ensure that we wait for some amount of time if specified in the .plan
        wait_for = self._waypoints[self._current_waypoint]["wait_for"]
        if wait_for > 0:
            await asyncio.sleep(wait_for)

        return "next_waypoint"

    @state(name="hide_rover")
    async def hide_rover(self, vehicle: Vehicle):
        # head to hiding location and stop the script
        logger.info("Hiding")
        hide_coords = Coordinate(
            self._hide_latitude,
            self._hide_longitude,
            vehicle.position.alt,
        )
        await vehicle.goto_coordinates(
            hide_coords,
            target_heading=self._default_heading,
        )
        logger.info("done!")
        return
