"""
Tests for app.services.routing_service:
- get_routes / check_route against a mocked OSRM server (no real network calls)
- compute_impact against the real (rolled-back) test database
"""
import asyncio
from datetime import datetime, timezone
from typing import Callable

import httpx
import pytest
from cachetools import TTLCache
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.traffic_event import TrafficEvent
from app.models.pipeline_alert import PipelineAlert
from app.schemas.routing import LatLng
from app.services import routing_service
from app.services.routing_service import RoutingError, check_route, compute_impact, get_routes

ORIGIN = LatLng(lat=47.612, lng=-122.337)
DESTINATION = LatLng(lat=47.643, lng=-122.300)


def _osrm_ok_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": "Ok",
            "routes": [
                {
                    "geometry": {
                        "coordinates": [
                            [ORIGIN.lng, ORIGIN.lat],
                            [DESTINATION.lng, DESTINATION.lat],
                        ]
                    },
                    "distance": 4200.0,
                    "duration": 600.0,
                }
            ],
        },
    )


def _osrm_no_route_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"code": "NoRoute", "routes": []})


def _osrm_server_error_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, text="internal error")


def _counting_transport(
    response_handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[httpx.MockTransport, list[int]]:
    """A MockTransport that also records how many times it was actually called."""
    calls: list[int] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return response_handler(request)

    return httpx.MockTransport(_handler), calls


@pytest.mark.asyncio
async def test_get_routes_parses_successful_osrm_response():
    transport = httpx.MockTransport(_osrm_ok_response)
    async with httpx.AsyncClient(transport=transport) as client:
        routes = await get_routes(client, ORIGIN, DESTINATION)

    assert len(routes) == 1
    assert routes[0].distance_meters == 4200.0
    assert routes[0].duration_seconds == 600.0
    assert routes[0].geometry[0] == ORIGIN
    assert routes[0].geometry[-1] == DESTINATION


@pytest.mark.asyncio
async def test_get_routes_raises_on_no_route():
    transport = httpx.MockTransport(_osrm_no_route_response)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(RoutingError):
            await get_routes(client, ORIGIN, DESTINATION)


@pytest.mark.asyncio
async def test_get_routes_raises_on_upstream_http_error():
    transport = httpx.MockTransport(_osrm_server_error_response)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(RoutingError):
            await get_routes(client, ORIGIN, DESTINATION)


@pytest.mark.asyncio
async def test_get_routes_raises_when_server_unreachable():
    def _raise_connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(_raise_connect_error)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(RoutingError):
            await get_routes(client, ORIGIN, DESTINATION)


# ---------------------------------------------------------------------------
# OSRM route cache (Phase C)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_routes_cache_hit_does_not_reinvoke_osrm():
    transport, calls = _counting_transport(_osrm_ok_response)
    async with httpx.AsyncClient(transport=transport) as client:
        first = await get_routes(client, ORIGIN, DESTINATION)
        second = await get_routes(client, ORIGIN, DESTINATION)

    assert len(calls) == 1
    assert second == first


@pytest.mark.asyncio
async def test_get_routes_different_destination_is_not_served_from_others_cache_entry():
    transport, calls = _counting_transport(_osrm_ok_response)
    other_destination = LatLng(lat=DESTINATION.lat + 1.0, lng=DESTINATION.lng + 1.0)
    async with httpx.AsyncClient(transport=transport) as client:
        await get_routes(client, ORIGIN, DESTINATION)
        await get_routes(client, ORIGIN, other_destination)

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_get_routes_cache_expires_after_ttl(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(routing_service, "_osrm_cache", TTLCache(maxsize=500, ttl=1))

    transport, calls = _counting_transport(_osrm_ok_response)
    async with httpx.AsyncClient(transport=transport) as client:
        await get_routes(client, ORIGIN, DESTINATION)
        await asyncio.sleep(1.2)
        await get_routes(client, ORIGIN, DESTINATION)

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_get_routes_cache_evicts_least_recently_used_over_capacity(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(routing_service, "_osrm_cache", TTLCache(maxsize=2, ttl=300))

    transport, calls = _counting_transport(_osrm_ok_response)
    dest_a = DESTINATION
    dest_b = LatLng(lat=DESTINATION.lat + 1.0, lng=DESTINATION.lng + 1.0)
    dest_c = LatLng(lat=DESTINATION.lat + 2.0, lng=DESTINATION.lng + 2.0)

    async with httpx.AsyncClient(transport=transport) as client:
        await get_routes(client, ORIGIN, dest_a)  # miss - cache: {a}
        await get_routes(client, ORIGIN, dest_b)  # miss - cache: {a, b}
        await get_routes(client, ORIGIN, dest_a)  # hit - marks 'a' most-recently-used
        await get_routes(client, ORIGIN, dest_c)  # miss, over capacity - evicts 'b' (LRU), not 'a'
        await get_routes(client, ORIGIN, dest_a)  # still cached - hit
        await get_routes(client, ORIGIN, dest_b)  # was evicted - miss

    # 4 misses (a, b, c, b-again) + 2 hits that made no HTTP call at all.
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_get_routes_error_response_is_not_cached():
    responses = [_osrm_no_route_response, _osrm_ok_response]

    def _first_error_then_ok(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)(request)

    transport, calls = _counting_transport(_first_error_then_ok)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(RoutingError):
            await get_routes(client, ORIGIN, DESTINATION)
        # If the failed lookup had been cached, this would raise RoutingError
        # again instead of reaching the mock a second time.
        await get_routes(client, ORIGIN, DESTINATION)

    assert len(calls) == 2


@pytest.mark.db
@pytest.mark.asyncio
async def test_compute_impact_flags_nearby_alert_and_ignores_far_alert(db_session: AsyncSession):
    near_event = TrafficEvent(
        source="test",
        road_name="I-90",
        segment_key="test:near",
        lat=ORIGIN.lat,
        lng=ORIGIN.lng,
        speed_kph=20.0,
        observed_at=datetime.now(timezone.utc),
    )
    far_event = TrafficEvent(
        source="test",
        road_name="Somewhere Else",
        segment_key="test:far",
        lat=ORIGIN.lat + 5.0,
        lng=ORIGIN.lng + 5.0,
        speed_kph=20.0,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add_all([near_event, far_event])
    await db_session.flush()

    near_alert = PipelineAlert(
        type="traffic",
        message="Nearby incident",
        severity=4,
        confidence=0.8,
        related_traffic_event_id=near_event.id,
    )
    far_alert = PipelineAlert(
        type="traffic",
        message="Distant incident",
        severity=4,
        confidence=0.8,
        related_traffic_event_id=far_event.id,
    )
    db_session.add_all([near_alert, far_alert])
    await db_session.commit()

    route_geometry = [ORIGIN, DESTINATION]
    impacted = await compute_impact(db_session, route_geometry)

    messages = {a.message for a in impacted}
    assert "Nearby incident" in messages
    assert "Distant incident" not in messages


@pytest.mark.db
@pytest.mark.asyncio
async def test_impact_stays_fresh_when_route_geometry_is_served_from_cache(db_session: AsyncSession):
    """
    The one case that actually protects against silently stale alerts:
    get_routes()'s geometry may be cache-hit on the second check_route() call,
    but compute_impact() must still reflect an alert inserted in between.
    """
    transport, calls = _counting_transport(_osrm_ok_response)

    async with httpx.AsyncClient(transport=transport) as client:
        first = await check_route(db_session, client, ORIGIN, DESTINATION)
        assert first.routes[0].impacted_alerts == []

        event = TrafficEvent(
            source="test",
            road_name="I-90",
            segment_key="test:fresh-impact",
            lat=ORIGIN.lat,
            lng=ORIGIN.lng,
            speed_kph=15.0,
            observed_at=datetime.now(timezone.utc),
        )
        db_session.add(event)
        await db_session.flush()
        db_session.add(
            PipelineAlert(
                type="traffic",
                message="New incident after first check",
                severity=5,
                confidence=0.9,
                related_traffic_event_id=event.id,
            )
        )
        await db_session.commit()

        second = await check_route(db_session, client, ORIGIN, DESTINATION)

    # Only one real OSRM call - the second check_route() hit the geometry cache.
    assert len(calls) == 1
    messages = {a.message for a in second.routes[0].impacted_alerts}
    assert "New incident after first check" in messages
