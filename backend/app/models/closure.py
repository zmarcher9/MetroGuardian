"""
Closure model: construction and road closures.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Closure(Base):
    """
    Represents construction or road closure (lane closure, full closure, detour).
    """

    __tablename__ = "closures"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. "city_feed", "mock"
    road_name: Mapped[str] = mapped_column(Text, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    closure_type: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "lane_closure", "full_closure", "detour"
    severity: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # e.g. 1–3
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    # Relationships
    alerts = relationship("Alert", back_populates="related_closure", foreign_keys="Alert.related_closure_id")
