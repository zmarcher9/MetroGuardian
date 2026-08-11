"""
Tests for app.services.routing_service:
- get_routes / check_route against a mocked OSRM server (no real network calls)
- compute_impact against the real (rolled-back) test database
"""
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.traffic_event import TrafficEvent
from app.models.pipeline_alert import PipelineAlert
from app.schemas.routing import LatLng
from app.services.routing_service import RoutingError, compute_impact, get_routes

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
