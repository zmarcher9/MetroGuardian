from __future__ import annotations

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.routing import RouteCheckRequest, RouteCheckResponse
from app.services.routing_service import RoutingError, check_route

router = APIRouter(tags=["routing"])
logger = logging.getLogger(__name__)

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/route/check", response_model=RouteCheckResponse)
async def route_check(body: RouteCheckRequest, db: DbDep) -> RouteCheckResponse:
    """
    Fetch driving route(s) between origin and destination, and flag any recent
    traffic/construction alerts that fall near each route.
    """
    async with httpx.AsyncClient() as client:
        try:
            result = await check_route(db, client, body.origin, body.destination)
        except RoutingError as e:
            logger.warning("Route check failed", extra={"error": str(e)})
            raise HTTPException(status_code=502, detail=str(e)) from e

    return RouteCheckResponse(routes=result.routes, recommended_index=result.recommended_index)
