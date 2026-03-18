from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, AsyncGenerator

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.pipeline_alert import PipelineAlert

router = APIRouter(tags=["realtime"])
logger = logging.getLogger(__name__)

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _sse(data: dict, *, event: str = "message") -> str:
    # SSE format: event:<name>\ndata:<json>\n\n
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _alert_payload(r: PipelineAlert) -> dict:
    return {
        "id": str(r.id),
        "type": r.type,
        "message": r.message,
        "severity": r.severity,
        "confidence": r.confidence,
        "created_at": r.created_at,
        "related_traffic_event_id": str(r.related_traffic_event_id) if r.related_traffic_event_id else None,
        "related_construction_event_id": str(r.related_construction_event_id)
        if r.related_construction_event_id
        else None,
    }


def _is_newer(r: PipelineAlert, last_created_at, last_id) -> bool:
    if last_id is None or last_created_at is None:
        return False
    return (r.created_at, str(r.id)) > (last_created_at, str(last_id))


@router.get("/alerts/stream")
async def stream_alerts(
    request: Request,
    db: DbDep,
    poll_seconds: Annotated[float, Query(ge=0.25, le=10.0)] = 1.0,
) -> AsyncGenerator[str, None]:
    """
    Server-Sent Events endpoint for real-time alert updates.

    Client example:
      const es = new EventSource("/api/v1/alerts/stream");
      es.addEventListener("alert", (e) => console.log(JSON.parse(e.data)));
    """
    # Send a hello event so client knows it's connected.
    yield _sse({"status": "connected"}, event="hello")

    last_created_at = None
    last_id = None

    while True:
        if await request.is_disconnected():
            logger.info("SSE client disconnected")
            return

        q = select(PipelineAlert).order_by(desc(PipelineAlert.created_at)).limit(25)
        rows = (await db.execute(q)).scalars().all()
        if rows:
            newest = rows[0]
            if last_id is None:
                last_id = newest.id
                last_created_at = newest.created_at
            else:
                # Emit any alerts newer than the last seen marker.
                new_rows = [r for r in reversed(rows) if _is_newer(r, last_created_at, last_id)]
                for r in new_rows:
                    yield _sse(_alert_payload(r), event="alert")
                last_id = newest.id
                last_created_at = newest.created_at

        await asyncio.sleep(poll_seconds)

