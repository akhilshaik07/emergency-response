"""ResidentProfile model extending User for community residents."""

import enum
import uuid
from datetime import date
from typing import Optional, Any, List, Dict
from sqlalchemy import (
    String,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.base import Base


class ResidentStatusEnum(str, enum.Enum):
    """Resident availability / status enum."""
    active = "active"
    away = "away"
    deactivated = "deactivated"


class ResidentProfile(Base):
    """Profile table extending User with resident-specific metadata.

    NOTE ON 1:1 ENFORCEMENT:
    The unique=True constraint on user_id is load-bearing at the database level,
    guaranteeing that exactly one ResidentProfile can exist for a given User record.
    """
    __tablename__ = "resident_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # 1:1 relationship with users table
    # CASCADE DELETION: If the user record is deleted, the resident profile has no meaning.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Flat assignment
    # ON DELETE SET NULL: Deleting or reorganizing a flat must NOT delete the resident's
    # profile, identity, emergency contacts, or SOS incident audit trail.
    flat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flats.id", ondelete="SET NULL"),
        nullable=True,
    )

    date_of_birth: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
    )
    photo_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    status: Mapped[ResidentStatusEnum] = mapped_column(
        Enum(ResidentStatusEnum, name="resident_status_enum"),
        default=ResidentStatusEnum.active,
        server_default=text("'active'"),
        nullable=False,
    )

    # UNCONFIRMED FACULTY REQUIREMENT SCAFFOLDING:
    # Denormalized proximity cache storing pre-computed or nearby residents/volunteers.
    # Assumed payload shape:
    # [{"user_id": "<uuid>", "name": "...", "flat": "...", "distance_m": ...}]
    # NOTE: Normalized tables (flats, resident_profiles, volunteer_profiles) remain the single
    # source of truth. This field may be stale or empty (None) at any time; no application
    # subsystem should treat its absence as a fatal error.
    nearby_neighbours: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="resident_profile")
    flat: Mapped[Optional["Flat"]] = relationship("Flat", backref="residents")

    def __repr__(self) -> str:
        return f"<ResidentProfile id={self.id} user_id={self.user_id} status={self.status.value}>"


# Import for type annotations
from app.models.user import User  # noqa: E402
from app.models.society import Flat  # noqa: E402
