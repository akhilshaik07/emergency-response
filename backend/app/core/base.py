"""SQLAlchemy 2.0 Base declarative class for all database models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all future domain models."""
    pass
