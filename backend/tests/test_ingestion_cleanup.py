from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.construction_event import ConstructionEvent
from app.models.pipeline_alert import PipelineAlert
from app.models.traffic_event import TrafficEvent
from app.services.ingestion_cleanup import cleanup_old_ingestion_data

pytestmark = pytest.mark.db

settings = get_settings()


@pytest.mark.asyncio
async def test_cleanup_removes_old_traffic_and_construction_events(db_session: AsyncSession):
    now = datetime.now(timezone.utc)

    old_traffic = TrafficEvent(
        source="test",
        road_name="Old Rd",
        segment_key="test:old",
        lat=47.6,
        lng=-122.3,
        speed_kph=40.0,
        observed_at=now - timedelta(days=settings.traffic_event_retention_days + 1),
    )
    recent_traffic = TrafficEvent(
        source="test",
        road_name="Recent Rd",
        segment_key="test:recent",
        lat=47.6,
        lng=-122.3,
        speed_kph=40.0,
        observed_at=now,
    )
    old_construction = ConstructionEvent(
        source="test",
        road_name="Old Construction Rd",
        lat=47.6,
        lng=-122.3,
        description="Old lane closure",
        keyword="lane_closed",
        start_time=now,
        ingested_at=now - timedelta(days=settings.construction_event_retention_days + 1),
    )
    recent_construction = ConstructionEvent(
        source="test",
        road_name="Recent Construction Rd",
        lat=47.6,
        lng=-122.3,
        description="Recent lane closure",
        keyword="lane_closed",
        start_time=now,
        ingested_at=now,
    )
    db_session.add_all([old_traffic, recent_traffic, old_construction, recent_construction])
    await db_session.commit()

    result = await cleanup_old_ingestion_data(db_session)
    assert result.traffic_events_deleted >= 1
    assert result.construction_events_deleted >= 1

    remaining_traffic = {r.road_name for r in (await db_session.execute(select(TrafficEvent))).scalars().all()}
    remaining_construction = {
        r.road_name for r in (await db_session.execute(select(ConstructionEvent))).scalars().all()
    }
    assert "Old Rd" not in remaining_traffic
    assert "Recent Rd" in remaining_traffic
    assert "Old Construction Rd" not in remaining_construction
    assert "Recent Construction Rd" in remaining_construction


@pytest.mark.asyncio
async def test_cleanup_keeps_pipeline_alerts_within_their_much_longer_window(db_session: AsyncSession):
    now = datetime.now(timezone.utc)

    # Older than TrafficEvent's retention, but well within PipelineAlert's -
    # this is exactly the differentiated-retention behavior being tested.
    alert_age = timedelta(days=settings.traffic_event_retention_days + 1)
    assert alert_age < timedelta(days=settings.pipeline_alert_retention_days)

    mid_age_alert = PipelineAlert(
        type="traffic",
        message="Mid-age alert - should survive",
        severity=3,
        confidence=0.7,
        created_at=now - alert_age,
    )
    very_old_alert = PipelineAlert(
        type="traffic",
        message="Very old alert - should be purged",
        severity=3,
        confidence=0.7,
        created_at=now - timedelta(days=settings.pipeline_alert_retention_days + 1),
    )
    db_session.add_all([mid_age_alert, very_old_alert])
    await db_session.commit()

    result = await cleanup_old_ingestion_data(db_session)
    assert result.pipeline_alerts_deleted >= 1

    remaining_messages = {r.message for r in (await db_session.execute(select(PipelineAlert))).scalars().all()}
    assert "Mid-age alert - should survive" in remaining_messages
    assert "Very old alert - should be purged" not in remaining_messages
