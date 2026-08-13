"""
Pydantic schemas for saved routes.

SavedRoute stores flat origin_lat/origin_lng/dest_lat/dest_lng columns (see
app/models/saved_route.py), but the API exposes them as nested LatLng - the
schemas below own that conversion (SavedRouteResponse.from_model / the
flat-column kwargs a create endpoint passes into the ORM row), matching how
LatLng is used everywhere else in this codebase (app/schemas/routing.py).
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.saved_route import SavedRoute
from app.schemas.routing import LatLng


class SavedRouteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    origin: LatLng
    dest: LatLng
    waypoints: list[LatLng] | None = Field(default=None, max_length=50)


class SavedRouteResponse(BaseModel):
    id: UUID
    name: str
    origin: LatLng
    dest: LatLng
    waypoints: list[LatLng] | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, row: SavedRoute) -> "SavedRouteResponse":
        return cls(
            id=row.id,
            name=row.name,
            origin=LatLng(lat=row.origin_lat, lng=row.origin_lng),
            dest=LatLng(lat=row.dest_lat, lng=row.dest_lng),
            waypoints=[LatLng(**w) for w in row.waypoints] if row.waypoints else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
