from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class RouteCheckRequest(BaseModel):
    origin: LatLng
    destination: LatLng


class ImpactedAlertResponse(BaseModel):
    id: UUID
    type: str
    message: str
    severity: int
    created_at: datetime
    lat: float
    lng: float
    distance_meters: float

    model_config = {"from_attributes": True}


class RouteOptionResponse(BaseModel):
    geometry: list[LatLng]
    distance_meters: float
    duration_seconds: float
    impact_score: float
    impacted_alerts: list[ImpactedAlertResponse]


class RouteCheckResponse(BaseModel):
    routes: list[RouteOptionResponse]
    recommended_index: int
