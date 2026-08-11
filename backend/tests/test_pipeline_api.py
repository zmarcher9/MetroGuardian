from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.construction_event import ConstructionEvent
from app.models.pipeline_alert import PipelineAlert
from app.models.traffic_event import TrafficEvent

pytestmark = pytest.mark.db


@pytest.mark.asyncio
async def test_list_alerts_returns_seeded_alert(client: AsyncClient, db_session: AsyncSession):
    alert = PipelineAlert(
        type="traffic",
        message="Test seeded alert",
        severity=3,
        confidence=0.7,
    )
    db_session.add(alert)
    await db_session.commit()

    resp = await client.get("/api/v1/alerts")
    assert resp.status_code == 200
    messages = [a["message"] for a in resp.json()]
    assert "Test seeded alert" in messages


@pytest.mark.asyncio
async def test_get_alert_by_id(client: AsyncClient, db_session: AsyncSession):
    alert = PipelineAlert(type="construction", message="Specific alert", severity=2, confidence=0.5)
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    resp = await client.get(f"/api/v1/alerts/{alert.id}")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Specific alert"


@pytest.mark.asyncio
async def test_get_alert_404_for_unknown_id(client: AsyncClient):
    resp = await client.get(f"/api/v1/alerts/{uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_traffic_events_returns_seeded_event(client: AsyncClient, db_session: AsyncSession):
    event = TrafficEvent(
        source="test",
        road_name="Test Rd",
        segment_key="test:seed:1",
        lat=47.6,
        lng=-122.3,
        speed_kph=42.0,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    await db_session.commit()

    resp = await client.get("/api/v1/traffic-events")
    assert resp.status_code == 200
    road_names = [e["road_name"] for e in resp.json()]
    assert "Test Rd" in road_names


@pytest.mark.asyncio
async def test_list_construction_events_returns_seeded_event(client: AsyncClient, db_session: AsyncSession):
    event = ConstructionEvent(
        source="test",
        road_name="Test Construction Rd",
        lat=47.6,
        lng=-122.3,
        description="Lane closed for testing",
        keyword="lane_closed",
        start_time=datetime.now(timezone.utc),
        ingested_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    await db_session.commit()

    resp = await client.get("/api/v1/construction-events")
    assert resp.status_code == 200
    road_names = [e["road_name"] for e in resp.json()]
    assert "Test Construction Rd" in road_names


@pytest.mark.asyncio
async def test_ingest_traffic_endpoint_inserts_events(client: AsyncClient):
    resp = await client.post("/api/v1/ingest/traffic")
    assert resp.status_code == 200
    body = resp.json()
    assert body["inserted_events"] == 3
    assert body["generated_alerts"] >= 0


@pytest.mark.asyncio
async def test_ingest_construction_endpoint_inserts_events(client: AsyncClient):
    resp = await client.post("/api/v1/ingest/construction")
    assert resp.status_code == 200
    body = resp.json()
    assert body["inserted_events"] >= 1
