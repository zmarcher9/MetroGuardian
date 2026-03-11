"""
Incident model: detected probable incidents from traffic data.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Incident(Base):
    """
    Represents a detected probable incident from traffic speed data.
    Severity typically 1–5 based on speed drop.
    """

    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. "simulated", "traffic_api_x"
    road_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # e.g. 1–5 based on speed drop
    speed_before: Mapped[float] = mapped_column(Float, nullable=False)
    speed_after: Mapped[float] = mapped_column(Float, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")  # e.g. "active", "cleared"

    # Relationships
    alerts = relationship("Alert", back_populates="related_incident", foreign_keys="Alert.related_incident_id")
