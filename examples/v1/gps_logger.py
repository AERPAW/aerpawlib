"""
Periodically check the current node's position over time and dump it to a CSV file.

By default, this samples at 1Hz and saves to a file named GPS_DATA_YYYY-MM-DD_HH:MM:SS.csv

The file format is below:
    line,longitude,latitude,altitude,voltage,YYYY-MM-DD HH:MM:SS.000000,gps status,satellites

Usage:
    python -m aerpawlib gps_logger --conn <connection>

    python -m aerpawlib gps_logger --conn <connection> --output <filename> --samplerate <Hz>

Requirements:
    dronekit
"""

import csv
import datetime
import os
import signal
import time
from argparse import ArgumentParser

from aerpawlib.v1.runner import BasicRunner, entrypoint
from aerpawlib.v1.vehicle import Vehicle


def _log(s: str) -> None:
    print(f"{datetime.datetime.now()}: {s}")


def _dump(vehicle: Vehicle, line_num: int, writer: object) -> None:
    position_relative = vehicle.position
    lat, lon = [str(i) for i in [position_relative.lat, position_relative.lon]]
    alt = round(float(str(position_relative.alt)), 3)

    batt = str(vehicle.battery)
    volt = float(batt[16 : batt.find(",")])

    timestamp = datetime.datetime.now()

    fix, num_sat = vehicle.gps.fix_type, vehicle.gps.satellites_visible

    # special case for no lock
    # -999 is safe because it's literally impossible in all cases (as opposed to -1)
    if fix < 2:
        lat, lon, alt = -999, -999, -999

    vel = vehicle.velocity
    attitude = vehicle.attitude
    attitude_str = "(" + ",".join(map(str, [attitude.pitch, attitude.yaw, attitude.roll])) + ")"

    # If you ever update this list of parameters logged please also change
    #  ../../PostProcessing/log2csv.py    and
    #  ../aerpawlib/examples/preplanned_trajectory.py
    # to keep them in sync

    writer.writerow([line_num, lon, lat, alt, attitude_str, vel, volt, timestamp, fix, num_sat])

    _log(f"[DEBUG] {line_num}, {lat}, {lon}, {alt}, {attitude_str}, {vel}, {volt}, {timestamp}, {fix}, {num_sat}")


def periodic_dump(vehicle: Vehicle, filename: str, sample_rate: int) -> None:
    """
    Periodically grab the state of the vehicle on a given port and dump it to
    a CSV file with the given filename.

    Output format:
    line,lon,lat,alt,batt voltage,timestamp,gps status,satellites
    """
    sampling_delay = 1 / sample_rate
    next_sample = 0

    f = open(filename, "w+")
    cur_line = sum(1 for _ in f) + 1
    writer = csv.writer(f)

    # make sure that we close gracefully when asked
    logging = True

    def _clean_up(_, __):
        nonlocal logging
        logging = False

    signal.signal(signal.SIGINT, _clean_up)
    signal.signal(signal.SIGTERM, _clean_up)

    while logging:
        if time.time() > next_sample:
            next_sample = time.time() + sampling_delay
            if not vehicle.connected:
                _log("[WARN] No vehicle heartbeat")
                continue
            _dump(vehicle, cur_line, writer)
            f.flush()
            os.fsync(f)
            cur_line += 1
        time.sleep(sampling_delay / 4)

    f.close()


class LoggerRunner(BasicRunner):
    def initialize_args(self, extra_args: list[str]):
        default_file = f"GPS_DATA_{datetime.datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}.csv"

        parser = ArgumentParser()
        parser.add_argument("--output", help="output file", required=False, default=default_file)
        parser.add_argument(
            "-r",
            "--samplerate",
            help="samples per second (Hz)",
            required=False,
            default=1,
        )
        self.args = parser.parse_args(extra_args)

    @entrypoint
    async def collect_logs(self, vehicle: Vehicle):
        periodic_dump(vehicle, self.args.output, int(self.args.samplerate))
