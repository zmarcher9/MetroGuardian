"""
Routing service: OSRM route lookup + route-impact analysis against recent pipeline alerts.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
from cachetools import TTLCache
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.construction_event import ConstructionEvent
from app.models.pipeline_alert import PipelineAlert
from app.models.traffic_event import TrafficEvent
from app.schemas.routing import ImpactedAlertResponse, LatLng, RouteOptionResponse

logger = logging.getLogger(__name__)

_EARTH_RADIUS_M = 6_371_000.0

# Caches get_routes()'s result (road-network geometry/distance/duration only -
# never compute_impact()'s live alert scoring, which must stay fresh on every
# call). A single module-level instance, mirroring the module-level dicts in
# app/core/rate_limit.py: built once from settings, mutated in place
# thereafter (never reassigned), so no `global` is needed anywhere in this
# file. Tests that need a different ttl/maxsize than the configured default
# monkeypatch this object directly (`monkeypatch.setattr(routing_service,
# "_osrm_cache", TTLCache(...))`) rather than going through settings.
_osrm_cache: TTLCache = TTLCache(
    maxsize=get_settings().osrm_cache_max_entries, ttl=get_settings().osrm_cache_ttl_seconds
)


def _clear_osrm_cache() -> None:
    """Test-only: drop all cached OSRM route lookups."""
    _osrm_cache.clear()


def _osrm_cache_key(origin: LatLng, destination: LatLng) -> tuple[float, float, float, float]:
    # ~11m precision. OSRM snaps input coordinates to the nearest road
    # segment before routing, so two origins this close together
    # overwhelmingly resolve to the same route - this is a "close enough,
    # road-snapped" cache key by design, not a guarantee of literal input
    # coordinates.
    return (round(origin.lat, 4), round(origin.lng, 4), round(destination.lat, 4), round(destination.lng, 4))


class RoutingError(Exception):
    """Raised when the upstream OSRM server can't produce a route."""


@dataclass(frozen=True)
class OsrmRoute:
    geometry: list[LatLng]
    distance_meters: float
    duration_seconds: float


@dataclass(frozen=True)
class RouteCheckResult:
    routes: list[RouteOptionResponse] = field(default_factory=list)
    recommended_index: int = 0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _project_meters(origin: LatLng, point: LatLng) -> tuple[float, float]:
    """Local equirectangular projection (meters) around `origin`. Fine at city scale."""
    lat_rad = math.radians(origin.lat)
    x = math.radians(point.lng - origin.lng) * math.cos(lat_rad) * _EARTH_RADIUS_M
    y = math.radians(point.lat - origin.lat) * _EARTH_RADIUS_M
    return x, y


def _point_to_segment_distance_m(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    px, py = p
    ax, ay = a
    bx, by = b
    abx, aby = bx - ax, by - ay
    seg_len_sq = abx * abx + aby * aby
    if seg_len_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / seg_len_sq))
    closest_x, closest_y = ax + t * abx, ay + t * aby
    return math.hypot(px - closest_x, py - closest_y)


def _min_distance_to_route_m(point: LatLng, route_geometry: list[LatLng]) -> float:
    if not route_geometry:
        return float("inf")
    origin = route_geometry[0]
    p = _project_meters(origin, point)
    projected = [_project_meters(origin, v) for v in route_geometry]
    if len(projected) == 1:
        return math.hypot(p[0] - projected[0][0], p[1] - projected[0][1])
    return min(
        _point_to_segment_distance_m(p, projected[i], projected[i + 1])
        for i in range(len(projected) - 1)
    )


async def get_routes(client: httpx.AsyncClient, origin: LatLng, destination: LatLng) -> list[OsrmRoute]:
    """
    Fetch driving routes (with alternatives, if OSRM offers any) between origin and destination.

    Successful results are cached in-process for settings.osrm_cache_ttl_seconds
    (see _osrm_cache) - the public OSRM demo server has no SLA and enforces
    usage limits, and repeated checks of the same trip don't need a fresh
    lookup every time. Errors are never cached.
    """
    key = _osrm_cache_key(origin, destination)
    cached = _osrm_cache.get(key)
    if cached is not None:
        # A shallow copy: the cached list is shared across every caller with
        # this key, so returning it directly would let one caller's in-place
        # mutation of the list corrupt what every other caller sees.
        return list(cached)

    settings = get_settings()
    coords = f"{origin.lng},{origin.lat};{destination.lng},{destination.lat}"
    url = f"{settings.osrm_base_url}/route/v1/driving/{coords}"
    params = {"alternatives": "true", "overview": "full", "geometries": "geojson"}

    try:
        resp = await client.get(url, params=params, timeout=10.0)
    except httpx.HTTPError as e:
        raise RoutingError(f"Could not reach routing server: {e}") from e

    if resp.status_code != 200:
        raise RoutingError(f"Routing server returned HTTP {resp.status_code}")

    data = resp.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"Routing server could not find a route: {data.get('code', 'unknown error')}")

    routes: list[OsrmRoute] = []
    for r in data["routes"]:
        coordinates = r["geometry"]["coordinates"]  # [[lng, lat], ...]
        geometry = [LatLng(lat=c[1], lng=c[0]) for c in coordinates]
        routes.append(
            OsrmRoute(
                geometry=geometry,
                distance_meters=float(r["distance"]),
                duration_seconds=float(r["duration"]),
            )
        )
    _osrm_cache[key] = routes
    return routes


async def _recent_alerts_with_location(db: AsyncSession) -> list[tuple[PipelineAlert, float, float]]:
    settings = get_settings()
    cutoff = _utc_now() - timedelta(minutes=settings.route_impact_lookback_minutes)

    traffic_q = (
        select(PipelineAlert, TrafficEvent.lat, TrafficEvent.lng)
        .join(TrafficEvent, PipelineAlert.related_traffic_event_id == TrafficEvent.id)
        .where(PipelineAlert.created_at >= cutoff)
    )
    construction_q = (
        select(PipelineAlert, ConstructionEvent.lat, ConstructionEvent.lng)
        .join(ConstructionEvent, PipelineAlert.related_construction_event_id == ConstructionEvent.id)
        .where(PipelineAlert.created_at >= cutoff)
    )

    traffic_rows = (await db.execute(traffic_q)).all()
    construction_rows = (await db.execute(construction_q)).all()
    return [(a, lat, lng) for a, lat, lng in [*traffic_rows, *construction_rows]]


def _location_key(alert_type: str, lat: float, lng: float) -> tuple[str, float, float]:
    # Round to ~11m precision so repeated detections of the same ongoing
    # incident (the ingestion loop re-fires an alert every cycle it's still
    # active) collapse into a single entry instead of stacking up.
    return (alert_type, round(lat, 4), round(lng, 4))


async def compute_impact(db: AsyncSession, route_geometry: list[LatLng]) -> list[ImpactedAlertResponse]:
    settings = get_settings()
    candidates = await _recent_alerts_with_location(db)

    by_location: dict[tuple[str, float, float], ImpactedAlertResponse] = {}
    for alert, lat, lng in candidates:
        point = LatLng(lat=lat, lng=lng)
        distance = _min_distance_to_route_m(point, route_geometry)
        if distance > settings.route_impact_radius_meters:
            continue

        key = _location_key(alert.type, lat, lng)
        candidate = ImpactedAlertResponse(
            id=alert.id,
            type=alert.type,
            message=alert.message,
            severity=alert.severity,
            created_at=alert.created_at,
            lat=lat,
            lng=lng,
            distance_meters=round(distance, 1),
        )
        # Keep only the most recent detection for a given incident location.
        existing = by_location.get(key)
        if existing is None or candidate.created_at > existing.created_at:
            by_location[key] = candidate

    impacted = list(by_location.values())
    impacted.sort(key=lambda a: a.distance_meters)
    return impacted


def _impact_score(impacted_alerts: list[ImpactedAlertResponse]) -> float:
    return sum(a.severity for a in impacted_alerts)


async def check_route(db: AsyncSession, client: httpx.AsyncClient, origin: LatLng, destination: LatLng) -> RouteCheckResult:
    osrm_routes = await get_routes(client, origin, destination)

    options: list[RouteOptionResponse] = []
    for r in osrm_routes:
        impacted_alerts = await compute_impact(db, r.geometry)
        options.append(
            RouteOptionResponse(
                geometry=r.geometry,
                distance_meters=r.distance_meters,
                duration_seconds=r.duration_seconds,
                impact_score=_impact_score(impacted_alerts),
                impacted_alerts=impacted_alerts,
            )
        )

    recommended_index = min(range(len(options)), key=lambda i: (options[i].impact_score, i)) if options else 0
    return RouteCheckResult(routes=options, recommended_index=recommended_index)
