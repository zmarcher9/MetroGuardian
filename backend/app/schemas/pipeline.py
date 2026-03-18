from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TrafficEventResponse(BaseModel):
    id: UUID
    source: str
    road_name: str
    segment_key: str
    lat: float
    lng: float
    speed_kph: float
    observed_at: datetime

    model_config = {"from_attributes": True}


class ConstructionEventResponse(BaseModel):
    id: UUID
    source: str
    road_name: str
    lat: float
    lng: float
    description: str
    keyword: str | None
    start_time: datetime
    end_time: datetime | None
    ingested_at: datetime

    model_config = {"from_attributes": True}


class PipelineAlertResponse(BaseModel):
    id: UUID
    type: str
    message: str
    severity: int = Field(ge=1, le=5)
    confidence: float | None = Field(default=None, ge=0, le=1)
    related_traffic_event_id: UUID | None
    related_construction_event_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class IngestionRunResponse(BaseModel):
    inserted_events: int
    generated_alerts: int

