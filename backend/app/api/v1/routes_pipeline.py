from typing import Annotated
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.construction_event import ConstructionEvent
from app.models.pipeline_alert import PipelineAlert
from app.models.traffic_event import TrafficEvent
from app.schemas.pipeline import (
    ConstructionEventResponse,
    IngestionRunResponse,
    PipelineAlertResponse,
    TrafficEventResponse,
)
from app.services.ingestion import ingest_construction, ingest_traffic

router = APIRouter(tags=["pipeline"])
logger = logging.getLogger(__name__)


DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/ingest/traffic")
async def run_traffic_ingestion(db: DbDep) -> IngestionRunResponse:
    result = await ingest_traffic(db)
    return IngestionRunResponse(inserted_events=result.inserted_events, generated_alerts=result.generated_alerts)


@router.post("/ingest/construction")
async def run_construction_ingestion(db: DbDep) -> IngestionRunResponse:
    result = await ingest_construction(db)
    return IngestionRunResponse(inserted_events=result.inserted_events, generated_alerts=result.generated_alerts)


@router.get("/alerts")
async def list_alerts(
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[PipelineAlertResponse]:
    rows = (await db.execute(select(PipelineAlert).order_by(desc(PipelineAlert.created_at)).limit(limit))).scalars().all()
    return [PipelineAlertResponse.model_validate(r) for r in rows]


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: UUID, db: DbDep) -> PipelineAlertResponse:
    row = (await db.execute(select(PipelineAlert).where(PipelineAlert.id == alert_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return PipelineAlertResponse.model_validate(row)


@router.get("/traffic-events")
async def list_traffic_events(
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[TrafficEventResponse]:
    rows = (await db.execute(select(TrafficEvent).order_by(desc(TrafficEvent.observed_at)).limit(limit))).scalars().all()
    return [TrafficEventResponse.model_validate(r) for r in rows]


@router.get("/construction-events")
async def list_construction_events(
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[ConstructionEventResponse]:
    rows = (
        await db.execute(select(ConstructionEvent).order_by(desc(ConstructionEvent.ingested_at)).limit(limit))
    ).scalars().all()
    return [ConstructionEventResponse.model_validate(r) for r in rows]

