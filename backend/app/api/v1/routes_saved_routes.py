from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.saved_route import SavedRoute
from app.models.user import User
from app.schemas.saved_routes import SavedRouteCreate, SavedRouteResponse

router = APIRouter(prefix="/saved-routes", tags=["saved-routes"])
logger = logging.getLogger(__name__)

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_saved_route(body: SavedRouteCreate, db: DbDep, current_user: CurrentUserDep) -> SavedRouteResponse:
    settings = get_settings()
    # Count-then-insert, not locked: two concurrent POSTs from the same user
    # could both pass this check and both insert, exceeding the cap by a
    # small margin under real concurrency. Accepted - this is a soft
    # backstop against unbounded row growth, not a security boundary.
    count_result = await db.execute(
        select(func.count()).select_from(SavedRoute).where(SavedRoute.user_id == current_user.id)
    )
    if count_result.scalar_one() >= settings.saved_routes_max_per_user:
        logger.info("Saved route rejected: user at cap", extra={"user_id": str(current_user.id)})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Cannot save more than {settings.saved_routes_max_per_user} routes",
        )

    row = SavedRoute(
        user_id=current_user.id,
        name=body.name,
        origin_lat=body.origin.lat,
        origin_lng=body.origin.lng,
        dest_lat=body.dest.lat,
        dest_lng=body.dest.lng,
        waypoints=[w.model_dump() for w in body.waypoints] if body.waypoints is not None else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return SavedRouteResponse.from_model(row)


@router.get("")
async def list_saved_routes(
    db: DbDep,
    current_user: CurrentUserDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[SavedRouteResponse]:
    rows = (
        await db.execute(
            select(SavedRoute)
            .where(SavedRoute.user_id == current_user.id)
            # id tiebreaker: created_at is Python-side (not DB-generated), so
            # two rows created in the same instant would otherwise sort
            # nondeterministically.
            .order_by(desc(SavedRoute.created_at), desc(SavedRoute.id))
            .limit(limit)
        )
    ).scalars().all()
    return [SavedRouteResponse.from_model(r) for r in rows]


@router.get("/{route_id}")
async def get_saved_route(route_id: UUID, db: DbDep, current_user: CurrentUserDep) -> SavedRouteResponse:
    row = (
        await db.execute(
            select(SavedRoute).where(SavedRoute.id == route_id, SavedRoute.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved route not found")
    return SavedRouteResponse.from_model(row)


@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_route(route_id: UUID, db: DbDep, current_user: CurrentUserDep) -> None:
    row = (
        await db.execute(
            select(SavedRoute).where(SavedRoute.id == route_id, SavedRoute.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved route not found")
    await db.delete(row)
    await db.commit()
