"""ResidentProfile model extending User for community residents."""

import enum
import uuid
from datetime import date
from typing import Optional
from sqlalchemy import (
    String,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
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
