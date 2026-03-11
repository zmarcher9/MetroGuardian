"""
SQLAlchemy declarative base for MetroGuardian models.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models. All tables inherit from this."""

    pass
