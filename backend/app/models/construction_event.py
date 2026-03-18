"""
ConstructionEvent model: raw construction/closure feed items ingested from CSV/JSON/static sources.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConstructionEvent(Base):
    __tablename__ = "construction_events"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )

    source: Mapped[str] = mapped_column(String(128), nullable=False, default="static_feed")
    road_name: Mapped[str] = mapped_column(Text, nullable=False)

    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)

    description: Mapped[str] = mapped_column(Text, nullable=False)
    keyword: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False, index=True)

