"""
Unit tests for the pure geometry helpers in routing_service (no network, no DB).
"""
import math

from app.schemas.routing import LatLng
from app.services.routing_service import (
    _min_distance_to_route_m,
    _point_to_segment_distance_m,
    _project_meters,
)


def test_project_meters_origin_maps_to_zero():
    origin = LatLng(lat=47.61, lng=-122.33)
    x, y = _project_meters(origin, origin)
    assert math.isclose(x, 0.0, abs_tol=1e-6)
    assert math.isclose(y, 0.0, abs_tol=1e-6)


def test_project_meters_one_degree_latitude_is_about_111km():
    origin = LatLng(lat=47.0, lng=-122.0)
    north = LatLng(lat=48.0, lng=-122.0)
    _, y = _project_meters(origin, north)
    assert 110_000 < y < 112_000


def test_point_to_segment_distance_endpoint_degenerate_segment():
    # a == b: distance collapses to point-to-point distance
    a = (0.0, 0.0)
    d = _point_to_segment_distance_m((3.0, 4.0), a, a)
    assert math.isclose(d, 5.0)


def test_point_to_segment_distance_perpendicular():
    a = (0.0, 0.0)
    b = (10.0, 0.0)
    # Point directly "above" the midpoint of the segment
    d = _point_to_segment_distance_m((5.0, 3.0), a, b)
    assert math.isclose(d, 3.0)


def test_point_to_segment_distance_beyond_endpoint_clamps():
    a = (0.0, 0.0)
    b = (10.0, 0.0)
    # Point beyond `b`, distance should be to `b`, not the infinite line
    d = _point_to_segment_distance_m((15.0, 0.0), a, b)
    assert math.isclose(d, 5.0)


def test_min_distance_to_route_empty_geometry_is_infinite():
    point = LatLng(lat=47.61, lng=-122.33)
    assert _min_distance_to_route_m(point, []) == float("inf")


def test_min_distance_to_route_single_point_geometry():
    origin = LatLng(lat=47.61, lng=-122.33)
    point = LatLng(lat=47.61, lng=-122.33)
    d = _min_distance_to_route_m(point, [origin])
    assert math.isclose(d, 0.0, abs_tol=1e-6)


def test_min_distance_to_route_picks_nearest_segment():
    # A simple straight route along the same latitude.
    route = [
        LatLng(lat=47.61, lng=-122.34),
        LatLng(lat=47.61, lng=-122.33),
        LatLng(lat=47.61, lng=-122.32),
    ]
    # A point right on the route should be ~0m away.
    on_route = LatLng(lat=47.61, lng=-122.33)
    assert _min_distance_to_route_m(on_route, route) < 1.0

    # A point far from the route should be far away.
    far_away = LatLng(lat=47.70, lng=-122.33)
    assert _min_distance_to_route_m(far_away, route) > 5_000
