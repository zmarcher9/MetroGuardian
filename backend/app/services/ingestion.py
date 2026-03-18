from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.construction_event import ConstructionEvent
from app.models.pipeline_alert import PipelineAlert
from app.models.traffic_event import TrafficEvent

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class IngestionRunResult:
    inserted_events: int
    generated_alerts: int


_CONSTRUCTION_KEYWORDS: list[tuple[str, str]] = [
    ("lane closed", "lane_closed"),
    ("road closed", "road_closed"),
    ("detour", "detour"),
]


def _find_keyword(text: str) -> str | None:
    lowered = text.lower()
    for needle, label in _CONSTRUCTION_KEYWORDS:
        if needle in lowered:
            return label
    return None


def _severity_from_drop(drop_ratio: float) -> int:
    # drop_ratio is e.g. 0.42 for 42% drop
    if drop_ratio >= 0.70:
        return 5
    if drop_ratio >= 0.55:
        return 4
    if drop_ratio >= 0.40:
        return 3
    if drop_ratio >= 0.25:
        return 2
    return 1


async def ingest_traffic(db: AsyncSession, *, source: str = "simulated") -> IngestionRunResult:
    """
    Insert TrafficEvents and generate PipelineAlerts if speed drops by >40% within 5 minutes.
    """
    now = _utc_now()
    settings = get_settings()

    # Simple built-in simulated network
    segments = [
        ("I-90", "i90:wb:1", 47.6120, -122.3370),
        ("I-5", "i5:sb:3", 47.6205, -122.3230),
        ("SR-520", "sr520:eb:2", 47.6430, -122.3000),
    ]

    inserted = 0
    alerts = 0

    for road_name, segment_key, lat, lng in segments:
        # simulated baseline with occasional sharp drops
        baseline = random.uniform(55, 95)
        if settings.traffic_simulated and random.random() < 0.20:
            speed = max(5.0, baseline * random.uniform(0.2, 0.55))
        else:
            speed = baseline * random.uniform(0.85, 1.05)

        ev = TrafficEvent(
            source=source,
            road_name=road_name,
            segment_key=segment_key,
            lat=lat,
            lng=lng,
            speed_kph=float(round(speed, 2)),
            observed_at=now,
        )
        db.add(ev)
        await db.flush()  # ensures ev.id is populated
        inserted += 1

        # find a prior observation within 5 minutes for same segment
        cutoff = now - timedelta(minutes=5)
        q: Select[tuple[TrafficEvent]] = (
            select(TrafficEvent)
            .where(
                TrafficEvent.segment_key == segment_key,
                TrafficEvent.observed_at >= cutoff,
                TrafficEvent.id != ev.id,
            )
            .order_by(desc(TrafficEvent.observed_at))
            .limit(1)
        )
        prev = (await db.execute(q)).scalar_one_or_none()
        if prev is None:
            continue

        if prev.speed_kph <= 0:
            continue

        drop_ratio = (prev.speed_kph - ev.speed_kph) / prev.speed_kph
        if drop_ratio > 0.40:
            pa = PipelineAlert(
                type="traffic",
                message=(
                    f"Traffic anomaly on {road_name}: speed dropped from "
                    f"{prev.speed_kph:.1f} kph to {ev.speed_kph:.1f} kph in <5 min "
                    f"({drop_ratio*100:.0f}% drop)."
                ),
                severity=_severity_from_drop(drop_ratio),
                confidence=0.75,
                related_traffic_event_id=ev.id,
                related_construction_event_id=None,
            )
            db.add(pa)
            alerts += 1

    await db.commit()
    logger.info("Traffic ingestion completed", extra={"inserted_events": inserted, "generated_alerts": alerts})
    return IngestionRunResult(inserted_events=inserted, generated_alerts=alerts)


def _load_construction_feed() -> list[dict]:
    """
    Load a construction feed from Settings.construction_feed_path if provided,
    otherwise return a built-in sample list.
    """
    settings = get_settings()
    if settings.construction_feed_path:
        p = Path(settings.construction_feed_path)
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        raise ValueError("construction_feed_path must point to a JSON array")

    return [
        {
            "source": "sample",
            "road_name": "Pine St",
            "lat": 47.6100,
            "lng": -122.3340,
            "description": "Lane closed near 3rd Ave for utility work",
        },
        {
            "source": "sample",
            "road_name": "1st Ave",
            "lat": 47.6040,
            "lng": -122.3375,
            "description": "Detour in place due to event staging",
        },
    ]


async def ingest_construction(db: AsyncSession) -> IngestionRunResult:
    """
    Insert ConstructionEvents and generate PipelineAlerts when keyword thresholds are crossed.
    """
    feed = _load_construction_feed()
    now = _utc_now()

    inserted = 0
    alerts = 0

    for item in feed:
        desc_text = str(item.get("description") or "").strip()
        if not desc_text:
            continue

        keyword = _find_keyword(desc_text)
        ev = ConstructionEvent(
            source=str(item.get("source") or "static_feed"),
            road_name=str(item.get("road_name") or "unknown"),
            lat=float(item.get("lat") or 0.0),
            lng=float(item.get("lng") or 0.0),
            description=desc_text,
            keyword=keyword,
            start_time=now,
            end_time=None,
            ingested_at=now,
        )
        db.add(ev)
        await db.flush()
        inserted += 1

        if keyword is not None:
            pa = PipelineAlert(
                type="construction",
                message=f"Construction update on {ev.road_name}: {desc_text}",
                severity=3 if keyword in {"road_closed"} else 2,
                confidence=0.65,
                related_traffic_event_id=None,
                related_construction_event_id=ev.id,
            )
            db.add(pa)
            alerts += 1

    await db.commit()
    logger.info("Construction ingestion completed", extra={"inserted_events": inserted, "generated_alerts": alerts})
    return IngestionRunResult(inserted_events=inserted, generated_alerts=alerts)

