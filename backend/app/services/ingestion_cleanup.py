"""
Ingestion-data retention: the background ingestion loop (app/main.py) inserts
new TrafficEvent/ConstructionEvent rows every cycle (every 30s by default)
with no deduplication, forever - roughly 14,400 rows/day at the default
interval, regardless of whether anyone is using the app. Nothing in the app
ever reads a TrafficEvent/ConstructionEvent beyond a few minutes old (the
anomaly-detection lookback) or beyond the first "most recent N" page, so
short retention for those two is safe.

PipelineAlert is different: it's the data the "alert history" feature
(README roadmap v1.2) will eventually show, so it gets a much longer
retention window rather than being purged on the same short cycle.

Known tradeoff: PipelineAlert has no lat/lng of its own - it only gets one
via a join to the TrafficEvent/ConstructionEvent it references
(related_traffic_event_id/related_construction_event_id, see
routing_service.py's _recent_alerts_with_location). Once that source event
ages out (3 days) but the alert itself hasn't (90 days), the join stops
matching and the alert effectively loses its location. Nothing today notices
- the only two places that do this join look back 5 and 45 minutes,
respectively - but a future "alert history" UI that wants to show alerts on
a map would. The real fix at that point is denormalizing lat/lng onto
PipelineAlert at creation time (in ingestion.py) so alert history doesn't
depend on the source event surviving.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import cast

from sqlalchemy import delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.construction_event import ConstructionEvent
from app.models.pipeline_alert import PipelineAlert
from app.models.traffic_event import TrafficEvent


@dataclass(frozen=True)
class IngestionCleanupResult:
    traffic_events_deleted: int
    construction_events_deleted: int
    pipeline_alerts_deleted: int


async def _delete_older_than(db: AsyncSession, model, column, cutoff: datetime) -> int:
    result = cast(CursorResult, await db.execute(delete(model).where(column < cutoff)))
    return result.rowcount or 0


async def cleanup_old_ingestion_data(db: AsyncSession) -> IngestionCleanupResult:
    """Deletes ingestion rows past their retention window. Returns per-table counts deleted."""
    settings = get_settings()
    now = datetime.now(timezone.utc)

    traffic_deleted = await _delete_older_than(
        db, TrafficEvent, TrafficEvent.observed_at, now - timedelta(days=settings.traffic_event_retention_days)
    )
    construction_deleted = await _delete_older_than(
        db,
        ConstructionEvent,
        ConstructionEvent.ingested_at,
        now - timedelta(days=settings.construction_event_retention_days),
    )
    alerts_deleted = await _delete_older_than(
        db, PipelineAlert, PipelineAlert.created_at, now - timedelta(days=settings.pipeline_alert_retention_days)
    )
    await db.commit()

    return IngestionCleanupResult(
        traffic_events_deleted=traffic_deleted,
        construction_events_deleted=construction_deleted,
        pipeline_alerts_deleted=alerts_deleted,
    )
