from random import random

from aerpawlib.v1.util import Coordinate, inside, readGeofence

# Bounding box for placing the radio emitter
min_lat = 35.72245323013216
max_lat = 35.730246035887596

min_lon = -78.69107783437764
max_lon = -78.70096577054667


class RadioEmitter:
    """Emulates a radio emitter at a basic level. Chooses a random location
    for the emitter"""

    def __init__(self, geofence_file: str | None = None):
        """Initialize radio emitter, optionally within a geofence file"""
        if geofence_file:
            self.geofence = readGeofence(geofence_file)
        else:
            self.geofence = None
        self.set_random_emitter_pos()

    def set_random_emitter_pos(self):
        """Repeatedly pick a random location in the bounding box,
        until it is within the geofence"""
        while True:
            new_lat = min_lat + random() * (max_lat - min_lat)
            new_lon = min_lon + random() * (max_lon - min_lon)

            # If we don't have a geofence the first choice is valid
            if not self.geofence:
                self.emitter_pos = Coordinate(new_lat, new_lon, 0)
                break
            if inside(new_lon, new_lat, self.geofence):
                self.emitter_pos = Coordinate(new_lat, new_lon, 0)
                break

        print(f"Emitter position: {new_lat},{new_lon}")

    def get_power(self, vehicle_pos):
        """Get a mock power reading based on the vehicle position"""
        dist = abs(self.emitter_pos.distance(vehicle_pos))
        return -dist


if __name__ == "__main__":
    r = RadioEmitter()

    r.set_random_emitter_pos()
