"""Geofence KML must be one polygon without holes; anything else is rejected."""

import pytest

from aerpawlib.v1.util import read_geofence as read_v1
from aerpawlib.v2.geofence import read_geofence as read_v2

RING = "-78.70,35.72,0 -78.70,35.74,0 -78.69,35.74,0 -78.69,35.72,0 -78.70,35.72,0"


def _kml(body: str) -> str:
    return f'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>{body}</Document></kml>'


def _polygon(outer: str, inner: str | None = None) -> str:
    hole = f"<innerBoundaryIs><LinearRing><coordinates>{inner}</coordinates></LinearRing></innerBoundaryIs>" if inner else ""
    return f"<Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>{outer}</coordinates></LinearRing></outerBoundaryIs>{hole}</Polygon></Placemark>"


@pytest.fixture(params=[read_v1, read_v2], ids=["v1", "v2"])
def read(request):
    return request.param


def _write(tmp_path, body):
    path = tmp_path / "fence.kml"
    path.write_text(_kml(body))
    return str(path)


def test_single_polygon_loads(tmp_path, read):
    assert len(read(_write(tmp_path, _polygon(RING)))) == 5


def test_second_polygon_rejected(tmp_path, read):
    with pytest.raises(ValueError, match="exactly one Polygon"):
        read(_write(tmp_path, _polygon(RING) + _polygon(RING)))


def test_hole_rejected(tmp_path, read):
    inner = "-78.698,35.725,0 -78.698,35.73,0 -78.695,35.73,0 -78.698,35.725,0"
    with pytest.raises(ValueError, match="holes"):
        read(_write(tmp_path, _polygon(RING, inner)))


@pytest.mark.parametrize("bad", ["-78.70", "abc,35.7,0", "nan,35.7,0"])
def test_malformed_vertex_rejected(tmp_path, read, bad):
    with pytest.raises(ValueError):
        read(_write(tmp_path, _polygon(f"{RING} {bad}")))


def test_no_polygon_rejected(tmp_path, read):
    with pytest.raises(ValueError):
        read(_write(tmp_path, "<Placemark><Point><coordinates>-78.7,35.7,0</coordinates></Point></Placemark>"))
